# flake8: noqa: F403

from .fake_quantize import *  # noqa: F403
from .fuse_modules import fuse_modules  # noqa: F403
from .fuse_modules import fuse_modules_qat  # noqa: F403
from .fuser_method_mappings import *  # noqa: F403
from .observer import *  # noqa: F403
from .qconfig import *  # noqa: F403
from .qconfig_mapping import *  # noqa: F403
from .quant_type import *  # noqa: F403
from .quantization_mappings import *  # type: ignore[no-redef]
from .quantize import *  # noqa: F403
from .quantize_jit import *  # noqa: F403
from .stubs import *  # noqa: F403

__all__ = [
    "DeQuantStub",
    "FakeQuantize",
    "FakeQuantizeBase",
    "FixedQParamsFakeQuantize",
    "FixedQParamsObserver",
    "FusedMovingAvgObsFakeQuantize",
    "HistogramObserver",
    "MatchAllNode",
    "MinMaxObserver",
    "MovingAverageMinMaxObserver",
    "MovingAveragePerChannelMinMaxObserver",
    "NoopObserver",
    "ObserverBase",
    "Pattern",
    "PerChannelMinMaxObserver",
    "PlaceholderObserver",
    "QConfig",
    "QConfigAny",
    "QConfigDynamic",
    "QConfigMapping",
    "QuantStub",
    "QuantType",
    "QuantWrapper",
    "RecordingObserver",
    "ReuseInputObserver",
    "UniformQuantizationObserverBase",
    "add_quant_dequant",
    "convert",
    "convert_dynamic_jit",
    "convert_jit",
    "default_affine_fixed_qparams_fake_quant",
    "default_affine_fixed_qparams_observer",
    "default_debug_observer",
    "default_dynamic_fake_quant",
    "default_dynamic_quant_observer",
    "default_embedding_fake_quant",
    "default_embedding_fake_quant_4bit",
    "default_eval_fn",
    "default_fake_quant",
    "default_fixed_qparams_range_0to1_fake_quant",
    "default_fixed_qparams_range_0to1_observer",
    "default_fixed_qparams_range_neg1to1_fake_quant",
    "default_fixed_qparams_range_neg1to1_observer",
    "default_float_qparams_observer",
    "default_float_qparams_observer_4bit",
    "default_fused_act_fake_quant",
    "default_fused_per_channel_wt_fake_quant",
    "default_fused_wt_fake_quant",
    "default_histogram_fake_quant",
    "default_histogram_observer",
    "default_observer",
    "default_per_channel_weight_fake_quant",
    "default_per_channel_weight_observer",
    "default_placeholder_observer",
    "default_reuse_input_observer",
    "default_symmetric_fixed_qparams_fake_quant",
    "default_symmetric_fixed_qparams_observer",
    "default_weight_fake_quant",
    "default_weight_observer",
    "disable_fake_quant",
    "disable_observer",
    "enable_fake_quant",
    "enable_observer",
    "fuse_conv_bn",
    "fuse_conv_bn_jit",
    "fuse_conv_bn_relu",
    "fuse_convtranspose_bn",
    "fuse_linear_bn",
    "fuse_modules",
    "fuse_modules_qat",
    "fused_per_channel_wt_fake_quant_range_neg_127_to_127",
    "fused_wt_fake_quant_range_neg_127_to_127",
    "get_combined_dict",
    "get_default_compare_output_module_list",
    "get_default_custom_config_dict",
    "get_default_dynamic_quant_module_mappings",
    "get_default_dynamic_sparse_quant_module_mappings",
    "get_default_float_to_quantized_operator_mappings",
    "get_default_qat_module_mappings",
    "get_default_qat_qconfig",
    "get_default_qat_qconfig_dict",
    "get_default_qat_qconfig_mapping",
    "get_default_qconfig",
    "get_default_qconfig_dict",
    "get_default_qconfig_mapping",
    "get_default_qconfig_propagation_list",
    "get_default_static_quant_module_mappings",
    "get_default_static_quant_reference_module_mappings",
    "get_default_static_sparse_quant_module_mappings",
    "get_dynamic_quant_module_class",
    "get_embedding_qat_module_mappings",
    "get_embedding_static_quant_module_mappings",
    "get_fuser_method",
    "get_fuser_method_new",
    "get_observer_state_dict",
    "get_quantized_operator",
    "get_static_quant_module_class",
    "load_observer_state_dict",
    "no_observer_set",
    "per_channel_weight_observer_range_neg_127_to_127",
    "prepare",
    "prepare_dynamic_jit",
    "prepare_jit",
    "prepare_qat",
    "propagate_qconfig_",
    "qconfig_equals",
    "quantize",
    "quantize_dynamic",
    "quantize_dynamic_jit",
    "quantize_jit",
    "quantize_qat",
    "script_qconfig",
    "script_qconfig_dict",
    "swap_module",
    "weight_observer_range_neg_127_to_127",
]

def default_eval_fn(model, calib_data):
    r"""
    Default evaluation function takes a torch.utils.data.Dataset or a list of
    input Tensors and run the model on the dataset
    """
    for data, target in calib_data:
        model(data)