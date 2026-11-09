#################################################
parser: Lexing and parsing OpenType feature files
#################################################

.. currentmodule:: fontTools.feaLib

.. contents:: On this page:
    :local:

       
.. rubric:: Overview
   :heading-level: 2


The primary interface for processing ``.fea`` files is
:class:`fontTools.feaLib.parser.Parser`. At a lower level, the
:mod:`fontTools.feaLib.lexer` module implements feaLib's lexical
analysis of the ``.fea`` language syntax, augmented by several smaller
utility modules.

	     
Parsing
-------

.. currentmodule:: fontTools.feaLib.parser

A value record cannot combine variable scalars and non-NULL device adjustments.
Explicit ``<device NULL>`` entries may be used with variable scalars.

.. automodule:: fontTools.feaLib.parser
   :members:
   :undoc-members:
		       

Lexing
------

.. currentmodule:: fontTools.feaLib.lexer

.. automodule:: fontTools.feaLib.lexer
   :members:
   :undoc-members:
      
		       

fontTools.feaLib.variableScalar
-------------------------------

.. currentmodule:: fontTools.feaLib.variableScalar

.. automodule:: fontTools.feaLib.variableScalar
   :members:
   :undoc-members:
      
		       

fontTools.feaLib.location
-------------------------

.. currentmodule:: fontTools.feaLib.location

.. automodule:: fontTools.feaLib.location
   :members:
   :undoc-members:
      
