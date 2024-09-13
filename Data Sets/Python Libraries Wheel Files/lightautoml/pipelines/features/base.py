"""Basic classes for features generation."""

import logging

from copy import copy
from copy import deepcopy
from typing import Any
from typing import Callable
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

import numpy as np

from pandas import DataFrame
from pandas import Series

from ...dataset.base import LAMLDataset
from ...dataset.np_pd_dataset import NumpyDataset
from ...dataset.np_pd_dataset import PandasDataset
from ...dataset.roles import CategoryRole
from ...dataset.roles import ColumnRole
from ...dataset.roles import NumericRole
from ...transformers.base import ChangeRoles
from ...transformers.base import ColumnsSelector
from ...transformers.base import ConvertDataset
from ...transformers.base import LAMLTransformer
from ...transformers.base import SequentialTransformer
from ...transformers.base import UnionTransformer
from ...transformers.categorical import CatIntersectstions
from ...transformers.categorical import FreqEncoder
from ...transformers.categorical import LabelEncoder
from ...transformers.categorical import MultiClassTargetEncoder
from ...transformers.categorical import MultioutputTargetEncoder
from ...transformers.categorical import OrdinalEncoder
from ...transformers.categorical import TargetEncoder
from ...transformers.datetime import BaseDiff
from ...transformers.datetime import DateSeasons
from ...transformers.groupby import GroupByTransformer
from ...transformers.numeric import FillInf
from ...transformers.numeric import FillnaMedian
from ...transformers.numeric import QuantileBinning
from ..utils import get_columns_by_role
from ..utils import map_pipeline_names


NumpyOrPandas = Union[PandasDataset, NumpyDataset]

logger = logging.getLogger(__name__)


class FeaturesPipeline:
    """Abstract class.

    Analyze train dataset and create composite transformer
    based on subset of features.
    Instance can be interpreted like Transformer
    (look for :class:`~lightautoml.transformers.base.LAMLTransformer`)
    with delayed initialization (based on dataset metadata)
    Main method, user should define in custom pipeline is ``.create_pipeline``.
    For example, look at
    :class:`~lightautoml.pipelines.features.lgb_pipeline.LGBSimpleFeatures`.
    After FeaturePipeline instance is created, it is used like transformer
    with ``.fit_transform`` and ``.transform`` method.

    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pipes: List[Callable[[LAMLDataset], LAMLTransformer]] = [self.create_pipeline]
        self.sequential = False

    # TODO: visualize pipeline ?
    @property
    def input_features(self) -> List[str]:
        """Names of input features of train data."""
        return self._input_features

    @input_features.setter
    def input_features(self, val: List[str]):
        """Setter for input_features.

        Args:
            val: List of strings.

        """
        self._input_features = deepcopy(val)

    @property
    def output_features(self) -> List[str]:
        """List of feature names that produces _pipeline."""
        return self._pipeline.features

    @property
    def used_features(self) -> List[str]:
        """List of feature names from original dataset that was used to produce output."""
        mapped = map_pipeline_names(self.input_features, self.output_features)
        return list(set(mapped))

    def create_pipeline(self, train: LAMLDataset) -> LAMLTransformer:
        """Analyse dataset and create composite transformer.

        Args:
            train: Dataset with train data.

        Returns:  # noqa DAR202
            Composite transformer (pipeline).

        """
        raise NotImplementedError

    def fit_transform(self, train: LAMLDataset) -> LAMLDataset:
        """Create pipeline and then fit on train data and then transform.

        Args:
            train: Dataset with train data.

        Returns:
            Dataset with new features.

        """
        # TODO: Think about input/output features attributes
        self._input_features = train.features
        self._pipeline = self._merge_seq(train) if self.sequential else self._merge(train)

        return self._pipeline.fit_transform(train)

    def transform(self, test: LAMLDataset) -> LAMLDataset:
        """Apply created pipeline to new data.

        Args:
            test: Dataset with test data.

        Returns:
            Dataset with new features.

        """
        return self._pipeline.transform(test)

    def set_sequential(self, val: bool = True):  # noqa D102
        self.sequential = val
        return self

    def append(self, pipeline):  # noqa D102
        if isinstance(pipeline, FeaturesPipeline):
            pipeline = [pipeline]

        for _pipeline in pipeline:
            self.pipes.extend(_pipeline.pipes)

        return self

    def prepend(self, pipeline):  # noqa D102
        if isinstance(pipeline, FeaturesPipeline):
            pipeline = [pipeline]

        for _pipeline in reversed(pipeline):
            self.pipes = _pipeline.pipes + self.pipes

        return self

    def pop(self, i: int = -1) -> Optional[Callable[[LAMLDataset], LAMLTransformer]]:  # noqa D102
        if len(self.pipes) > 1:
            return self.pipes.pop(i)

    def _merge(self, data: LAMLDataset) -> LAMLTransformer:
        pipes = []
        for pipe in self.pipes:
            pipes.append(pipe(data))

        return UnionTransformer(pipes) if len(pipes) > 1 else pipes[-1]

    def _merge_seq(self, data: LAMLDataset) -> LAMLTransformer:
        pipes = []
        for pipe in self.pipes:
            _pipe = pipe(data)
            data = _pipe.fit_transform(data)
            pipes.append(_pipe)

        return SequentialTransformer(pipes) if len(pipes) > 1 else pipes[-1]


class EmptyFeaturePipeline(FeaturesPipeline):
    """Dummy feature pipeline - ``.fit_transform`` and transform do nothing."""

    def create_pipeline(self, train: LAMLDataset) -> LAMLTransformer:
        """Create empty pipeline.

        Args:
            train: Dataset with train data.

        Returns:
            Composite transformer (pipeline), that do nothing.

        """
        return LAMLTransformer()


class TabularDataFeatures:
    """Helper class contains basic features transformations for tabular data.

    This method can de shared by all tabular feature pipelines,
    to simplify ``.create_automl`` definition.
    """

    def __init__(self, **kwargs: Any):
        """Set default parameters for tabular pipeline constructor.

        Args:
            **kwargs: Additional parameters.

        """
        self.multiclass_te_co = 3
        self.top_intersections = 5
        self.max_intersection_depth = 3
        self.subsample = 10000
        self.random_state = 42
        self.feats_imp = None
        self.ascending_by_cardinality = False

        self.max_bin_count = 10
        self.sparse_ohe = "auto"

        self.groupby_types = ["delta_median", "delta_mean", "min", "max", "std", "mode", "is_mode"]
        self.groupby_triplets = []
        self.groupby_top_based_on = "cardinality"
        self.groupby_top_categorical = 3
        self.groupby_top_numerical = 3

        for k in kwargs:
            self.__dict__[k] = kwargs[k]

    @staticmethod
    def get_cols_for_datetime(train: NumpyOrPandas) -> Tuple[List[str], List[str]]:
        """Get datetime columns to calculate features.

        Args:
            train: Dataset with train data.

        Returns:
            2 list of features names - base dates and common dates.

        """
        base_dates = get_columns_by_role(train, "Datetime", base_date=True)
        datetimes = get_columns_by_role(train, "Datetime", base_date=False) + get_columns_by_role(
            train, "Datetime", base_date=True, base_feats=True
        )

        return base_dates, datetimes

    def get_datetime_diffs(self, train: NumpyOrPandas) -> Optional[LAMLTransformer]:
        """Difference for all datetimes with base date.

        Args:
            train: Dataset with train data.

        Returns:
            Transformer or ``None`` if no required features.

        """
        base_dates, datetimes = self.get_cols_for_datetime(train)
        if len(datetimes) == 0 or len(base_dates) == 0:
            return

        dt_processing = SequentialTransformer(
            [
                ColumnsSelector(keys=list(set(datetimes + base_dates))),
                BaseDiff(base_names=base_dates, diff_names=datetimes),
            ]
        )
        return dt_processing

    def get_datetime_seasons(
        self, train: NumpyOrPandas, outp_role: Optional[ColumnRole] = None
    ) -> Optional[LAMLTransformer]:
        """Get season params from dates.

        Args:
            train: Dataset with train data.
            outp_role: Role associated with output features.

        Returns:
            Transformer or ``None`` if no required features.

        """
        _, datetimes = self.get_cols_for_datetime(train)
        for col in copy(datetimes):
            if len(train.roles[col].seasonality) == 0 and train.roles[col].country is None:
                datetimes.remove(col)

        if len(datetimes) == 0:
            return

        if outp_role is None:
            outp_role = NumericRole(np.float32)

        date_as_cat = SequentialTransformer(
            [
                ColumnsSelector(keys=datetimes),
                DateSeasons(outp_role),
            ]
        )
        return date_as_cat

    @staticmethod
    def get_numeric_data(
        train: NumpyOrPandas,
        feats_to_select: Optional[List[str]] = None,
        prob: Optional[bool] = None,
    ) -> Optional[LAMLTransformer]:
        """Select numeric features.

        Args:
            train: Dataset with train data.
            feats_to_select: Features to handle. If ``None`` - default filter.
            prob: Probability flag.

        Returns:
            Transformer.

        """
        if feats_to_select is None:
            if prob is None:
                feats_to_select = get_columns_by_role(train, "Numeric")
            else:
                feats_to_select = get_columns_by_role(train, "Numeric", prob=prob)

        if len(feats_to_select) == 0:
            return

        num_processing = SequentialTransformer(
            [
                ColumnsSelector(keys=feats_to_select),
                ConvertDataset(dataset_type=NumpyDataset),
                ChangeRoles(NumericRole(np.float32)),
            ]
        )

        return num_processing

    @staticmethod
    def get_freq_encoding(
        train: NumpyOrPandas, feats_to_select: Optional[List[str]] = None
    ) -> Optional[LAMLTransformer]:
        """Get frequency encoding part.

        Args:
            train: Dataset with train data.
            feats_to_select: Features to handle. If ``None`` - default filter.

        Returns:
            Transformer.

        """
        if feats_to_select is None:
            feats_to_select = get_columns_by_role(train, "Category", encoding_type="freq")

        if len(feats_to_select) == 0:
            return

        cat_processing = SequentialTransformer(
            [
                ColumnsSelector(keys=feats_to_select),
                FreqEncoder(),
            ]
        )
        return cat_processing

    def get_ordinal_encoding(
        self, train: NumpyOrPandas, feats_to_select: Optional[List[str]] = None
    ) -> Optional[LAMLTransformer]:
        """Get order encoded part.

        Args:
            train: Dataset with train data.
            feats_to_select: Features to handle. If ``None`` - default filter.

        Returns:
            Transformer.

        """
        if feats_to_select is None:
            feats_to_select = get_columns_by_role(train, "Category", ordinal=True)

        if len(feats_to_select) == 0:
            return

        cat_processing = SequentialTransformer(
            [
                ColumnsSelector(keys=feats_to_select),
                OrdinalEncoder(subs=self.subsample, random_state=self.random_state),
            ]
        )
        return cat_processing

    def get_categorical_raw(
        self, train: NumpyOrPandas, feats_to_select: Optional[List[str]] = None
    ) -> Optional[LAMLTransformer]:
        """Get label encoded categories data.

        Args:
            train: Dataset with train data.
            feats_to_select: Features to handle. If ``None`` - default filter.

        Returns:
            Transformer.

        """
        if feats_to_select is None:
            feats_to_select = []
            for i in ["auto", "oof", "int", "ohe"]:
                feats_to_select.extend(get_columns_by_role(train, "Category", encoding_type=i))

        if len(feats_to_select) == 0:
            return

        cat_processing = [
            ColumnsSelector(keys=feats_to_select),
            LabelEncoder(subs=self.subsample, random_state=self.random_state),
        ]
        cat_processing = SequentialTransformer(cat_processing)
        return cat_processing

    def get_target_encoder(self, train: NumpyOrPandas) -> Optional[type]:
        """Get target encoder func for dataset.

        Args:
            train: Dataset with train data.

        Returns:
            Class

        """
        target_encoder = None
        if train.folds is not None:
            if train.task.name in ["binary", "reg"]:
                target_encoder = TargetEncoder
            elif (train.task.name == "multi:reg") or (train.task.name == "multilabel"):
                n_classes = train.target.shape[1]
                if n_classes <= self.multiclass_te_co:
                    target_encoder = MultioutputTargetEncoder

            else:
                n_classes = train.target.max() + 1
                if n_classes <= self.multiclass_te_co:
                    target_encoder = MultiClassTargetEncoder

        return target_encoder

    def get_binned_data(
        self, train: NumpyOrPandas, feats_to_select: Optional[List[str]] = None
    ) -> Optional[LAMLTransformer]:
        """Get encoded quantiles of numeric features.

        Args:
            train: Dataset with train data.
            feats_to_select: features to hanlde. If ``None`` - default filter.

        Returns:
            Transformer.

        """
        if feats_to_select is None:
            feats_to_select = get_columns_by_role(train, "Numeric", discretization=True)

        if len(feats_to_select) == 0:
            return

        binned_processing = SequentialTransformer(
            [
                ColumnsSelector(keys=feats_to_select),
                QuantileBinning(nbins=self.max_bin_count),
            ]
        )
        return binned_processing

    def get_categorical_intersections(
        self, train: NumpyOrPandas, feats_to_select: Optional[List[str]] = None
    ) -> Optional[LAMLTransformer]:
        """Get transformer that implements categorical intersections.

        Args:
            train: Dataset with train data.
            feats_to_select: features to handle. If ``None`` - default filter.

        Returns:
            Transformer.

        """
        if feats_to_select is None:

            categories = get_columns_by_role(train, "Category")
            feats_to_select = categories

            if len(categories) <= 1:
                return

            if self.max_intersection_depth <= 1 or self.top_intersections <= 1:
                return
            elif len(categories) > self.top_intersections:
                feats_to_select = self.get_top_categories(train, mode="cat_intersections", top_n=self.top_intersections)

        elif len(feats_to_select) <= 1:
            return

        cat_processing = [
            ColumnsSelector(keys=feats_to_select),
            CatIntersectstions(
                subs=self.subsample,
                random_state=self.random_state,
                max_depth=self.max_intersection_depth,
            ),
        ]
        cat_processing = SequentialTransformer(cat_processing)

        return cat_processing

    def get_uniques_cnt(self, train: NumpyOrPandas, feats: List[str]) -> Series:
        """Get unique values cnt.

        Args:
            train: Dataset with train data.
            feats: Features names.

        Returns:
            Series.

        """
        uns = []
        for col in feats:
            feat = Series(train[:, col].data)
            if self.subsample is not None and self.subsample < len(feat):
                feat = feat.sample(
                    n=int(self.subsample) if self.subsample > 1 else None,
                    frac=self.subsample if self.subsample <= 1 else None,
                    random_state=self.random_state,
                )

            un = feat.value_counts(dropna=False)
            uns.append(un.shape[0])

        return Series(uns, index=feats, dtype="int")

    def get_top_categories(self, train: NumpyOrPandas, mode: str, top_n: int = 5) -> List[str]:
        """Get top categories by importance.

        If feature importance is not defined,
        or feats has same importance - sort it by unique values counts.
        In second case init param ``ascending_by_cardinality``
        defines how - asc or desc.

        Args:
            train: Dataset with train data.
            mode: What feature generation mode is used. Can be "cat_intersections" or "groupby".
            top_n: Number of top categories.

        Returns:
            List.

        """
        assert mode in ["cat_intersections", "groupby"]
        cats = get_columns_by_role(train, "Category")
        if len(cats) == 0 or top_n == 0:
            return []
        elif len(cats) <= top_n:
            return cats
        df = DataFrame({"importance": 0, "cardinality": 0}, index=cats)
        # importance if defined
        if self.feats_imp is not None:
            feats_imp = Series(self.feats_imp.get_features_score()).sort_values(ascending=False)
            df["importance"] = feats_imp[feats_imp.index.isin(cats)]
            df["importance"].fillna(-np.inf)
        # check for cardinality
        df["cardinality"] = self.get_uniques_cnt(train, cats)
        # sort
        if mode == "groupby" and self.groupby_top_based_on == "cardinality" or self.feats_imp is None:
            df = df.sort_values(by="cardinality", ascending=self.ascending_by_cardinality)
        else:
            df = df.sort_values(by="importance", ascending=False)
        # get top n
        top = list(df.index[:top_n])
        return top

    def get_top_numeric(self, train: NumpyOrPandas, top_n: int = 5) -> List[str]:
        """Get top numeric features by importance.

        If feature importance is not defined,
        or feats has same importance - sort it by unique values counts.
        In second case init param ``ascending_by_cardinality``
        defines how - asc or desc.

        Args:
            train: Dataset with train data.
            top_n: Number of top numeric features.

        Returns:
            List.
        """
        nums = get_columns_by_role(train, "Numeric")
        if len(nums) == 0 or top_n == 0:
            return []
        elif len(nums) <= top_n:
            return nums
        df = DataFrame({"importance": 0, "cardinality": 0}, index=nums)
        # importance if defined
        if self.feats_imp is not None:
            feats_imp = Series(self.feats_imp.get_features_score()).sort_values(ascending=False)
            df["importance"] = feats_imp[feats_imp.index.isin(nums)]
            df["importance"].fillna(-np.inf)
        # check for cardinality
        df["cardinality"] = -self.get_uniques_cnt(train, nums)
        # sort
        if self.groupby_top_based_on == "cardinality" or self.feats_imp is None:
            df = df.sort_values(by="cardinality", ascending=self.ascending_by_cardinality)
        else:
            df = df.sort_values(by="importance", ascending=False)
        # get top n
        top = list(df.index[:top_n])
        return top

    def get_groupby(self, train: NumpyOrPandas) -> Optional[LAMLTransformer]:
        """Get transformer that calculates group by features.

        Amount of features is limited to ``self.top_group_by_categorical`` and ``self.top_group_by_numerical`` fields.

        Args:
            train: Dataset with train data.

        Returns:
            Transformer.
        """
        categorical_names = get_columns_by_role(train, "Category")
        numerical_names = get_columns_by_role(train, "Numeric")

        groupby_transformations = []
        if len(self.groupby_triplets) > 0:
            for group_col, feat_name, trans in self.groupby_triplets:
                categorical_cols = [] if feat_name in numerical_names else [feat_name]
                numeric_cols = [] if feat_name in categorical_names else [feat_name]
                if len(categorical_cols) + len(numeric_cols) == 0:
                    logging.info2("Feature is incorrect or dropped by preselector: {}".format(feat_name))
                    continue
                if group_col not in categorical_names:
                    logging.info2("Groupby column is incorrect or dropped by preselector: {}".format(group_col))
                    continue
                new_transformation = {
                    "group_col": group_col,
                    "categorical_cols": categorical_cols,
                    "numeric_cols": numeric_cols,
                    "used_transforms": [trans],
                }
                groupby_transformations.append(new_transformation)
        else:
            cat_feats_to_select = self.get_top_categories(train, "groupby", self.groupby_top_categorical)
            num_feats_to_select = self.get_top_numeric(train, self.groupby_top_numerical)
            # At least two categoricals or one categorical and one numeric
            if len(cat_feats_to_select) < 1:
                return
            if len(cat_feats_to_select) == 1 and len(num_feats_to_select) < 1:
                return
            # collect groupby_transformations
            for i, group_col in enumerate(cat_feats_to_select):
                new_transformation = {
                    "group_col": group_col,
                    "categorical_cols": cat_feats_to_select[:i] + cat_feats_to_select[i + 1 :],
                    "numeric_cols": num_feats_to_select,
                    "used_transforms": self.groupby_types,
                }
                groupby_transformations.append(new_transformation)

        groupby_processing = [
            SequentialTransformer(
                [
                    UnionTransformer(
                        [
                            SequentialTransformer(
                                [
                                    ColumnsSelector(keys=[trans["group_col"]] + trans["categorical_cols"]),
                                    LabelEncoder(subs=None, random_state=42),
                                    ChangeRoles(CategoryRole(int)),
                                ]
                            ),
                            SequentialTransformer(
                                [ColumnsSelector(keys=trans["numeric_cols"]), FillInf(), FillnaMedian()]
                            ),
                        ]
                    ),
                    GroupByTransformer(**trans),
                ]
            )
            for trans in groupby_transformations
        ]
        groupby_processing = UnionTransformer(groupby_processing)

        return groupby_processing
