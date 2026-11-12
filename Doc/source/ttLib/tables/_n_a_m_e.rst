``name``: Naming table
----------------------

The ``name`` table is an OpenType table.

TTX writes name records as text when XML 1.0 can represent their characters.
Records containing XML-unsafe characters or undecodable, XML-unsafe bytes use
``encoding="hex"`` to preserve the original bytes instead of replacing them.
Importing such records restores those bytes exactly. Existing text records and
their ``unicode`` attributes remain supported.

.. automodule:: fontTools.ttLib.tables._n_a_m_e
   :members:
   :undoc-members:

