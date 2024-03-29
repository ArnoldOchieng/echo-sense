# Author: Jeremy Gordon
# Version: 0.1
# Created: August 25, 2014
# Updated: August 25, 2014

import re
from google.appengine.ext import db
import datetime as _dt
from datetime import datetime
from pyparsing import Word, Keyword, alphas, ParseException, Literal, CaselessLiteral \
, Combine, Optional, nums, Or, Forward, ZeroOrMore, StringEnd, alphanums, oneOf \
, QuotedString, quotedString, removeQuotes, delimitedList, nestedExpr, Suppress, Group, Regex, operatorPrecedence \
, opAssoc
import math
import tools
from constants import *
import logging

class ExpressionParser(object):
    opMap = {
        "<" : lambda a,b : a < b,
        "<=" : lambda a,b : a <= b,
        ">" : lambda a,b : a > b,
        ">=" : lambda a,b : a >= b,
        "!=" : lambda a,b : a != b,
        "==" : lambda a,b : a == b,
        "AND" : lambda a,b : a and b,
        "OR" : lambda a,b : a or b
        # "NOT" : lambda x : not a
    }

    FUNCTIONS = [
        "SUM",
        "AVE",
        "MAX",
        "MIN",
        "COUNT",
        "ALARMS",
        "DISTANCE",
        "SQRT"
    ]

    def __init__(self, expr, column=None, analysis=None, verbose=False):
        logging.debug("Building expression parser for %s" % expr)
        self.verbose = verbose
        self.expr = expr
        self.column = column
        self.analysis = analysis
        self.record_list = []
        self.alarm_list = []
        self.record = None
        # TODO: Pass prior record for accurate calcuations such as distance
        # self.prior_batch_last_record = prior_batch_last_record
        self.pattern = self._getPattern()


    # Generator to extract operators and operands in pairs
    def operatorOperands(self, tokenlist):
        it = iter(tokenlist)
        while 1:
            try:
                yield (it.next(), it.next())
            except StopIteration:
                break

    def __evalCurrentValue(self, toks):
        return self.analysis.columnValue(self.column, 0)

    def __evalAggregateColumn(self, toks):
        column = toks[0]
        if not self.record_list:
            raise Exception("Can't evaluate aggregate column without record list")
        res = [r.columnValue(column) for r in self.record_list]
        return res

    def __evalSingleColumn(self, toks):
        column = toks[0]
        if not self.record:
            raise Exception("Can't evaluate single column with no record")
        val = self.record.columnValue(column)
        return val

    def __multOp(self, toks):
        value = toks[0]
        prod = value[0]
        for op,val in self.operatorOperands(value[1:]):
            if op == '*': prod *= val
            if op == '/': prod /= val
        return prod

    def __expOp(self, toks):
        value = toks[0]
        res = value[0]
        for op,val in self.operatorOperands(value[1:]):
            if op == '^': res = pow(res, val)
        return res

    def __addOp(self, toks):
        value = toks[0]
        sum = value[0]
        for op,val in self.operatorOperands(value[1:]):
            if op == '+': sum += val
            if op == '-': sum -= val
        return sum

    def __evalLogicOp(self, toks):
        args = toks[0]
        if self.verbose:
            logging.debug(args)
        val1 = args[0]
        for op, val in self.operatorOperands(args[1:]):
            fn = self.opMap[op]
            val2 = val
            val1 = fn(val1, val2)
        return val1

    def __evalComparisonOp(self, tokens):
        args = tokens[0]
        val1 = args[0]
        for op,val in self.operatorOperands(args[1:]):
            fn = self.opMap[op]
            val2 = val
            if not fn(val1,val2):
                break
            val1 = val2
        else:
            return True
        return False

    def __evalString(self, toks):
        val = toks[0]
        return str(val).upper().strip()

    def __evalConstant(self, toks):
        return float(toks[0])

    def __evalFunction(self, toks):
        val = toks[0]
        fnName = val[0].upper()
        args = val[1:]
        args = [arg for arg in args if arg is not None]  # Filter nones
        if not args:
            return 0
        if fnName == 'SUM':
            return sum(args)
        elif fnName == 'AVE':
            from tools import average
            return average(args)
        elif fnName == 'MAX':
            return max(args)
        elif fnName == "MIN":
            return min(args)
        elif fnName == "COUNT":
            return len(args)
        elif fnName == "ALARMS":
            return self.alarm_list
        elif fnName == "DISTANCE":
            dist = 0
            # self.prior_batch_last_record.columnValue()
            last_gp = None
            for gp in args:
                gp = tools.safe_geopoint(gp)
                if last_gp and gp:
                    dist += tools.calcLocDistance(last_gp, gp)
                if gp:
                    last_gp = gp
            return dist  # m
        elif fnName == "SQRT":
            arg = args[0]
            return math.sqrt(arg)
        return 0


    def _getPattern(self):
        arith_expr = Forward()
        comp_expr = Forward()
        logic_expr = Forward()
        LPAR, RPAR, SEMI = map(Suppress, "();")
        identifier = Word(alphas+"_", alphanums+"_")
        multop = oneOf('* /')
        plusop = oneOf('+ -')
        expop = Literal( "^" )
        compop = oneOf('> < >= <= != ==')
        andop = Literal("AND")
        orop = Literal("OR")
        current_value = Literal( "." )
        assign = Literal( "=" )
        # notop = Literal('NOT')
        function = oneOf(' '.join(self.FUNCTIONS))
        function_call = Group(function.setResultsName('fn') + LPAR + Optional(delimitedList(arith_expr)) + RPAR)
        aggregate_column = QuotedString(quoteChar='{', endQuoteChar='}')
        single_column = QuotedString(quoteChar='[', endQuoteChar=']')
        integer = Regex(r"-?\d+")
        real = Regex(r"-?\d+\.\d*")

        # quotedString enables strings without quotes to pass

        operand = \
            function_call.setParseAction(self.__evalFunction) | \
            aggregate_column.setParseAction(self.__evalAggregateColumn) | \
            single_column.setParseAction(self.__evalSingleColumn) | \
            ((real | integer).setParseAction(self.__evalConstant)) | \
            quotedString.setParseAction(self.__evalString).addParseAction(removeQuotes) | \
            current_value.setParseAction(self.__evalCurrentValue) | \
            identifier.setParseAction(self.__evalString)

        arith_expr << operatorPrecedence(operand,
            [
             (expop, 2, opAssoc.LEFT, self.__expOp),
             (multop, 2, opAssoc.LEFT, self.__multOp),
             (plusop, 2, opAssoc.LEFT, self.__addOp),
            ])

        # comp_expr = Group(arith_expr + compop + arith_expr)
        comp_expr << operatorPrecedence(arith_expr,
            [
                (compop, 2, opAssoc.LEFT, self.__evalComparisonOp),
            ])

        logic_expr << operatorPrecedence(comp_expr,
            [
                (andop, 2, opAssoc.LEFT, self.__evalLogicOp),
                (orop, 2, opAssoc.LEFT, self.__evalLogicOp)
            ])

        pattern = logic_expr + StringEnd()
        return pattern

    def _parse_it(self):
        if self.expr:
            # logging.debug("Parsing: %s" % self.expr)
            # try parsing the input string
            try:
                L=self.pattern.parseString( self.expr )
            except ParseException, err:
                L=['Parse Failure',self.expr]
                if self.verbose:
                    logging.error('Parse Failure')
                    logging.error(err.line)
                    logging.error(" "*(err.column-1) + "^")
                    logging.error(err)
            except Exception, err:
                logging.error("Other error occurred: %s" % err)
            else:
                if self.verbose:
                    logging.debug("%s -> %s" % (self.expr, L[0]))
                return L[0]
        return None

    def run(self, record=None, record_list=None, alarm_list=None):
        self.record_list = record_list
        self.alarm_list = alarm_list
        self.record = record
        return self._parse_it()


