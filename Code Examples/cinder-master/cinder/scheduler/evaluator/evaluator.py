# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import operator
import re
import sys
from typing import Callable

import pyparsing

from cinder import exception
from cinder.i18n import _


def _operatorOperands(tokenList):
    it = iter(tokenList)
    while True:
        try:
            op1 = next(it)
            op2 = next(it)
            yield (op1, op2)
        except StopIteration:
            break


class EvalConstant(object):
    def __init__(self, toks):
        self.value = toks[0]

    def eval(self):
        result = self.value
        if (isinstance(result, str) and
                re.match(r"^[a-zA-Z_]+\.[a-zA-Z_]+$", result)):
            (which_dict, entry) = result.split('.')
            try:
                result = _vars[which_dict][entry]
            except KeyError:
                raise exception.EvaluatorParseException(
                    _("KeyError evaluating string"))
            except TypeError:
                raise exception.EvaluatorParseException(
                    _("TypeError evaluating string"))

        try:
            result = int(result)
        except ValueError:
            try:
                result = float(result)
            except ValueError:
                if isinstance(result, str):
                    result = result.replace('"', '').replace('\'', '')

        return result


class EvalSignOp(object):
    operations = {
        '+': 1,
        '-': -1,
    }

    def __init__(self, toks):
        self.sign, self.value = toks[0]

    def eval(self):
        return self.operations[self.sign] * self.value.eval()


class EvalAddOp(object):
    def __init__(self, toks):
        self.value = toks[0]

    def eval(self):
        sum = self.value[0].eval()
        for op, val in _operatorOperands(self.value[1:]):
            if op == '+':
                sum += val.eval()
            elif op == '-':
                sum -= val.eval()
        return sum


class EvalMultOp(object):
    def __init__(self, toks):
        self.value = toks[0]

    def eval(self):
        prod = self.value[0].eval()
        for op, val in _operatorOperands(self.value[1:]):
            try:
                if op == '*':
                    prod *= val.eval()
                elif op == '/':
                    prod /= float(val.eval())
            except ZeroDivisionError as e:
                raise exception.EvaluatorParseException(
                    _("ZeroDivisionError: %s") % e)
        return prod


class EvalPowerOp(object):
    def __init__(self, toks):
        self.value = toks[0]

    def eval(self):
        prod = self.value[0].eval()
        for op, val in _operatorOperands(self.value[1:]):
            prod = pow(prod, val.eval())
        return prod


class EvalNegateOp(object):
    def __init__(self, toks):
        self.negation, self.value = toks[0]

    def eval(self):
        return not self.value.eval()


class EvalComparisonOp(object):
    operations = {
        "<": operator.lt,
        "<=": operator.le,
        ">": operator.gt,
        ">=": operator.ge,
        "!=": operator.ne,
        "==": operator.eq,
        "<>": operator.ne,
    }

    def __init__(self, toks):
        self.value = toks[0]

    def eval(self):
        val1 = self.value[0].eval()
        for op, val in _operatorOperands(self.value[1:]):
            fn = self.operations[op]
            val2 = val.eval()
            if not fn(val1, val2):
                break
            val1 = val2
        else:
            return True
        return False


class EvalTernaryOp(object):
    def __init__(self, toks):
        self.value = toks[0]

    def eval(self):
        condition = self.value[0].eval()
        if condition:
            return self.value[2].eval()
        else:
            return self.value[4].eval()


class EvalFunction(object):
    functions: dict[str, Callable] = {
        "abs": abs,
        "max": max,
        "min": min,
    }

    def __init__(self, toks):
        self.func, self.value = toks[0]

    def eval(self):
        args = self.value.eval()
        if type(args) is list:
            return self.functions[self.func](*args)
        else:
            return self.functions[self.func](args)


class EvalCommaSeperator(object):
    def __init__(self, toks):
        self.value = toks[0]

    def eval(self):
        val1 = self.value[0].eval()
        val2 = self.value[2].eval()
        if type(val2) is list:
            val_list = []
            val_list.append(val1)
            for val in val2:
                val_list.append(val)
            return val_list

        return [val1, val2]


class EvalBoolAndOp(object):
    def __init__(self, toks):
        self.value = toks[0]

    def eval(self):
        left = self.value[0].eval()
        right = self.value[2].eval()
        return left and right


class EvalBoolOrOp(object):
    def __init__(self, toks):
        self.value = toks[0]

    def eval(self):
        left = self.value[0].eval()
        right = self.value[2].eval()
        return left or right


_parser = None
_vars = {}


def _def_parser():
    # Enabling packrat parsing greatly speeds up the parsing.
    pyparsing.ParserElement.enablePackrat()

    alphas = pyparsing.alphas
    Combine = pyparsing.Combine
    nums = pyparsing.nums
    quoted_string = pyparsing.quotedString

    oneOf = pyparsing.oneOf
    opAssoc = pyparsing.opAssoc
    infixNotation = pyparsing.infixNotation
    Word = pyparsing.Word

    integer = Word(nums)
    real = Combine(Word(nums) + '.' + Word(nums))
    variable = Word(alphas + '_' + '.')
    number = real | integer
    fn = Word(alphas + '_' + '.')
    operand = number | variable | fn | quoted_string

    signop = oneOf('+ -')
    addop = oneOf('+ -')
    multop = oneOf('* /')
    comparisonop = oneOf(' '.join(EvalComparisonOp.operations.keys()))
    ternaryop = ('?', ':')
    boolandop = oneOf('AND and &&')
    boolorop = oneOf('OR or ||')
    negateop = oneOf('NOT not !')

    operand.setParseAction(EvalConstant)
    expr = infixNotation(operand, [
        (fn, 1, opAssoc.RIGHT, EvalFunction),
        ("^", 2, opAssoc.RIGHT, EvalPowerOp),
        (signop, 1, opAssoc.RIGHT, EvalSignOp),
        (multop, 2, opAssoc.LEFT, EvalMultOp),
        (addop, 2, opAssoc.LEFT, EvalAddOp),
        (negateop, 1, opAssoc.RIGHT, EvalNegateOp),
        (comparisonop, 2, opAssoc.LEFT, EvalComparisonOp),
        (ternaryop, 3, opAssoc.LEFT, EvalTernaryOp),
        (boolandop, 2, opAssoc.LEFT, EvalBoolAndOp),
        (boolorop, 2, opAssoc.LEFT, EvalBoolOrOp),
        (',', 2, opAssoc.RIGHT, EvalCommaSeperator), ])

    return expr


def evaluate(expression, **kwargs):
    """Evaluates an expression.

    Provides the facility to evaluate mathematical expressions, and to
    substitute variables from dictionaries into those expressions.

    Supports both integer and floating point values, and automatic
    promotion where necessary.
    """
    global _parser
    if _parser is None:
        _parser = _def_parser()

    global _vars
    _vars = kwargs

    # Some reasonable formulas break with the default recursion limit of
    # 1000.  Raise it here and reset it afterward.
    orig_recursion_limit = sys.getrecursionlimit()
    if orig_recursion_limit < 3000:
        sys.setrecursionlimit(3000)

    try:
        result = _parser.parseString(expression, parseAll=True)[0]
    except pyparsing.ParseException as e:
        raise exception.EvaluatorParseException(
            _("ParseException: %s") % e)
    finally:
        sys.setrecursionlimit(orig_recursion_limit)

    return result.eval()
