from rayuela.base.semiring import Boolean, Real, Derivation , MaxPlus , Tropical
from rayuela.base.symbol import Sym, ε

from rayuela.fsa.fsa import FSA
from rayuela.fsa.state import State
from rayuela.fsa.transformer import Transformer as FSATransformer

from rayuela.cfg.cfg import CFG


R=Real

cfg=CFG(R, """
S -> S S
S -> a
S -> ε
""")

fsa = FSA(R, """
0 -[ε]-> 1
1 -[a]-> 2
2 -[ε]-> 3
2 -[ε]-> 2 0.3
4 -[a]-> 1
1 -[a]-> 1 0.4
1 -[ε]-> 1 0.4
""")

fsa.set_I(State(0), w=R(10))
fsa.add_F(State(3), w=R(10))
fsa.set_F(State(1), w=R(10))
fsa.set_I(State(4), w=R(10))

fsa
ftrans=FSATransformer()
fsa_e=ftrans.epsremoval(fsa)
fsa_e

#INTERSECTION WITH E-REMOVED AUTOMATON
ncfg=cfg.intersect_fsa(fsa_e)
print(ncfg.treesum())

ncfg=cfg.intersect_fsa_ε(fsa)
print(ncfg.treesum())