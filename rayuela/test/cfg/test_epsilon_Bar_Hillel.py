from rayuela.base.semiring import Boolean, Real, Derivation , MaxPlus , Tropical
from rayuela.base.symbol import Sym, ε

from rayuela.cfg.fsa import FSA
from rayuela.cfg.state import State
from rayuela.cfg.transformer import Transformer as FSATransformer

from rayuela.cfg.cfg import CFG


R=Real

cfg=CFG(R, """
S -> N L
N -> N N
N -> a
N -> b
O -> x
O -> +
L -> O N
""")

fsa = FSA(R, """
1 -[a]-> 2
2 -[+]-> 3
2 -[a]-> 2
3 -[b]-> 4
4 -[+]-> 1
4 -[b]-> 4
""")

fsa.set_I(State(1), w=R(10))
fsa.set_I(State(3), w=R(10))
# fsa.add_F(State(2), w=R(10))
fsa.set_F(State(4), w=R(10))
# fsa.set_I(State(3), w=R(10))

fsa
ftrans=FSATransformer()
fsa_e=ftrans.epsremoval(fsa)
fsa_e

#INTERSECTION WITH E-REMOVED AUTOMATON
ncfg=cfg.intersect_fsa(fsa_e)

print(ncfg.treesum())
print(ncfg.size)
ncfg=cfg.intersect_fsa_ε(fsa)
# print(ncfg.parse("a"))
print(ncfg)
print(ncfg.treesum())
print(cfg.size)
print(ncfg.size)