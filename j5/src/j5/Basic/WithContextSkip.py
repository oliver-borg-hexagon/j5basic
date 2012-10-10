#!/usr/bin/env python

"""Implementation of with block context managers that allow clearly defined skipping of the controlled block ala PEP 377

PEP 377 (rejected) proposed making this a standard language feature, and was rejected primarily because it alters the logical control flow of the with block.
This implementation uses the fact that variable assignments in the with ... as ...: syntax are considered part of the with block
Exceptions raised in these assignments are passed to the __exit__ function of the context manager, and can be used to skip the block.
"""

import threading
import contextlib
from functools import wraps
import sys
import warnings
from . import Singleton

class SkipStatement(Exception):
    pass

class StatementNotSkippedType:
    """A singleton object indicating that a context manager for a with clause has directed the receiving variable to cause the statement to be skipped"""
    __metaclass__ = Singleton.Singleton

class StatementSkippedType:
    """A singleton object indicating that a context manager for a with clause has directed the receiving variable to cause the statement to be skipped"""
    __metaclass__ = Singleton.Singleton

StatementSkipped = StatementSkippedType()
StatementNotSkipped = StatementNotSkippedType()

del StatementSkippedType
del StatementNotSkippedType

class SkipWarning(Warning):
    """Warning related to with context managers with conditional block skipping"""

class StatementSkippedDetectorType(object):
    """A singleton object used to detect whether a statement has been skipped or not"""
    __metaclass__ = Singleton.Singleton

    def __setattr__(self, attr, value):
        if isinstance(value, tuple) and len(value) == 2 and value[1] in (StatementSkipped, StatementNotSkipped):
            value = value[1]
        if value is StatementSkipped:
            raise SkipStatement()
        elif value is not StatementNotSkipped:
            warnings.warn("StatementSkippedDetector received an unexpected skip indicator", SkipWarning, stacklevel=2)

StatementSkippedDetector = StatementSkippedDetectorType()

class ConditionalContextManager(object):
    """Helper for @conditionalcontextmanager decorator."""
    def __init__(self, gen):
        self.gen = gen

    def __enter__(self):
        try:
            return self.gen.next(), StatementNotSkipped
        except SkipStatement, e:
            # set flag
            return StatementSkipped, StatementSkipped
        except StopIteration, e:
            raise RuntimeError("generator didn't yield or raise SkipStatement")

    def __exit__(self, type, value, traceback):
        if type is None:
            try:
                self.gen.next()
            except StopIteration:
                return
            else:
                raise RuntimeError("generator didn't stop")
        else:
            if value is None:
                # Need to force instantiation so we can reliably
                # tell if we get the same exception back
                value = type()
            if isinstance(value, SkipStatement):
                return True
            try:
                self.gen.throw(type, value, traceback)
                raise RuntimeError("generator didn't stop after throw()")
            except StopIteration, exc:
                # Suppress the exception *unless* it's the same exception that
                # was passed to throw().  This prevents a StopIteration
                # raised inside the "with" statement from being suppressed
                return exc is not value
            except:
                # only re-raise if it's *not* the exception that was
                # passed to throw(), because __exit__() must not raise
                # an exception unless __exit__() itself failed.  But throw()
                # has to raise the exception to signal propagation, so this
                # fixes the impedance mismatch between the throw() protocol
                # and the __exit__() protocol.
                #
                if sys.exc_info()[1] is not value:
                    raise


def conditionalcontextmanager(func):
    """@conditionalcontextmanager decorator.

    Typical usage:

        @conditionalcontextmanager
        def some_generator(<arguments>):
            <setup>
            try:
                if <condition>:
                    yield <value>
            finally:
                <cleanup>

    This makes this:

        with some_generator(<arguments>) as (<variable>, StatementSkippedDetector.<any_attr_name>):
            <body>

    equivalent to this:

        <setup>
        try:
            if <condition>:
                <variable> = <value>
                <body>
        finally:
            <cleanup>

    """
    @wraps(func)
    def helper(*args, **kwds):
        return ConditionalContextManager(func(*args, **kwds))
    return helper

