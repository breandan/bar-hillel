from typing import Dict, Type
from collections import defaultdict
from functools import reduce
from frozendict import frozendict

import numpy as np
from numpy import linalg as LA

from rayuela.base.datastructures import PriorityQueue
from rayuela.base.semiring import NullableSemiring, Semiring, nullable_semiring_builder
from rayuela.base.symbol import φ, Sym
from rayuela.fsa.state import State


class Strategy:
    VITERBI = 1
    BELLMANFORD = 2
    DIJKSTRA = 3
    LEHMANN = 4
    JOHNSON = 5
    FIXPOINT = 6
    DECOMPOSED_LEHMANN = 7
    VITERBI_FAILURE_ARCS = 8
    VITERBI_FAILURE_ARCS_CRF = 9


class Pathsum:
    def __init__(self, fsa):

        # basic FSA stuff
        self.fsa = fsa
        self.R = fsa.R
        self.N = self.fsa.num_states

        # state dictionary
        self.I = {}
        for n, q in enumerate(self.fsa.Q):
            self.I[q] = n

        # lift into the semiring
        self.W = self.lift()

    def _convert(self):
        mat = np.zeros((self.N, self.N))
        for n in range(self.N):
            for m in range(self.N):
                mat[n, m] = self.W[n, m].score
        return mat

    def max_eval(self):
        # computes the largest eigenvalue
        mat = self._convert()
        if len(mat) == 0:
            return 0.0
        vals = []
        for val in LA.eigvals(mat):
            vals.append(np.abs(val))
        return np.max(vals)

    def lift(self):
        """creates the weight matrix from the automaton"""
        W = self.R.zeros(self.N, self.N)
        for p in self.fsa.Q:
            for a, q, w in self.fsa.arcs(p):
                W[self.I[p], self.I[q]] += w
        return W

    def pathsum(self, strategy):
        if strategy == Strategy.DIJKSTRA:
            assert self.R.superior, "Dijkstra's requires a superior semiring"
            return self.dijkstra_early()

        elif strategy == Strategy.VITERBI:
            assert self.fsa.acyclic, "Viterbi requires an acyclic FSA"
            return self.viterbi_pathsum()

        elif strategy == Strategy.BELLMANFORD:
            assert self.R.idempotent, "Bellman-Ford requires an idempotent semiring"
            return self.bellmanford_pathsum()

        elif strategy == Strategy.JOHNSON:
            assert self.R.idempotent, "Johnson's requires an idempotent semiring"
            return self.johnson_pathsum()

        elif strategy == Strategy.LEHMANN:
            return self.lehmann_pathsum()

        elif strategy == Strategy.FIXPOINT:
            return self.fixpoint_pathsum()

        elif strategy == Strategy.DECOMPOSED_LEHMANN:
            return self.decomposed_lehmann_pathsum()

        elif strategy in [
            Strategy.VITERBI_FAILURE_ARCS,
            Strategy.VITERBI_FAILURE_ARCS_CRF,
        ]:
            return self.viterbi_φ_pathsum(strategy)

        else:
            raise NotImplementedError

    def forward(self, strategy):

        if strategy == Strategy.DIJKSTRA:
            assert self.R.superior, "Dijkstra's requires a superior semiring"
            return self.dijkstra_fwd()

        if strategy == Strategy.VITERBI:
            assert self.fsa.acyclic, "Viterbi requires an acyclic FSA"
            return self.viterbi_fwd()

        elif strategy == Strategy.BELLMANFORD:
            assert self.R.idempotent, "Bellman-Ford requires an idempotent semiring"
            return self.bellmanford_fwd()

        elif strategy == Strategy.JOHNSON:
            assert self.R.idempotent, "Johnson's requires an idempotent semiring"
            return self.johnson_fwd()

        elif strategy == Strategy.LEHMANN:
            return self.lehmann_fwd()

        elif strategy == Strategy.FIXPOINT:
            return self.fixpoint_fwd()

        else:
            raise NotImplementedError

    def backward(self, strategy):
        if strategy == Strategy.VITERBI:
            assert self.fsa.acyclic, "Viterbi requires an acyclic FSA"
            return self.viterbi_bwd()

        elif strategy == Strategy.BELLMANFORD:
            assert self.R.idempotent, "Bellman-Ford requires an idempotent semiring"
            return self.bellmanford_bwd()

        elif strategy == Strategy.JOHNSON:
            assert self.R.idempotent, "Johnson's requires an idempotent semiring"
            return self.johnson_bwd()

        elif strategy == Strategy.LEHMANN:
            return self.lehmann_bwd()

        elif strategy == Strategy.FIXPOINT:
            return self.fixpoint_bwd()

        elif strategy == Strategy.VITERBI_FAILURE_ARCS:
            return self.φ_backward_faster()

        elif strategy == Strategy.VITERBI_FAILURE_ARCS_CRF:
            return self.φ_backward_crf()

        else:
            raise NotImplementedError

    def allpairs(self, strategy=Strategy.LEHMANN, zero=True):
        if strategy == Strategy.VITERBI:
            assert self.fsa.acyclic, "Viterbi requires an acyclic FSA"

        elif strategy == Strategy.JOHNSON:
            assert self.R.idempotent, "Johnson's requires an idempotent semiring"
            return self.johnson()

        elif strategy == Strategy.LEHMANN:
            return self.lehmann(zero=zero)

        elif strategy == Strategy.FIXPOINT:
            raise self.fixpoint()

        else:
            raise NotImplementedError

    def allpairs_pathsum(self, W):
        pathsum = self.R.zero
        for p in self.fsa.Q:
            for q in self.fsa.Q:
                pathsum += self.fsa.λ[p] * W[p, q] * self.fsa.ρ[q]
        return pathsum

    def allpairs_fwd(self, W):
        α = self.R.chart()
        for p in self.fsa.Q:
            for q in self.fsa.Q:
                α[q] += self.fsa.λ[p] * W[p, q]
        return frozendict(α)

    def allpairs_bwd(self, W):
        𝜷 = self.R.chart()
        W = self.lehmann()
        for p in self.fsa.Q:
            for q in self.fsa.Q:
                𝜷[p] += W[p, q] * self.fsa.ρ[q]
        return frozendict(𝜷)

    def viterbi_pathsum(self):
        pathsum = self.R.zero
        𝜷 = self.viterbi_bwd()
        for q in self.fsa.Q:
            pathsum += self.fsa.λ[q] * 𝜷[q]
        return pathsum

    def viterbi_fwd(self):
        """The Viterbi algorithm run forwards."""

        assert self.fsa.acyclic

        # chart
        α = self.R.chart()

        # base case (paths of length 0)
        for q, w in self.fsa.I:
            α[q] = w

        # recursion
        for p in self.fsa.toposort(rev=False):
            for _, q, w in self.fsa.arcs(p):
                α[q] += α[p] * w

        return α

    def viterbi_bwd(self):
        """The Viterbi algorithm run backwards"""

        assert self.fsa.acyclic

        # chart
        𝜷 = self.R.chart()

        # base case (paths of length 0)
        for q, w in self.fsa.F:
            𝜷[q] = w

        # recursion
        for p in self.fsa.toposort(rev=True):
            for _, q, w in self.fsa.arcs(p):
                𝜷[p] += w * 𝜷[q]

        return 𝜷

    def dijkstra_early(self):
        """Dijkstra's algorithm with early stopping."""

        assert self.fsa.R.superior

        # initialization
        α = self.R.chart()
        agenda = PriorityQueue(R=self.fsa.R)
        popped = set([])

        # base case
        for q, w in self.fsa.I:
            agenda.push((q, False), w)

        # main loop
        while agenda:
            (i, stop), v = agenda.pop()

            if stop and stopearly:
                return v

            popped.add(i)
            α[i] += v
            for _, j, w in self.fsa.arcs(i):
                if j not in popped:
                    agenda.push((j, False), α[i] * w)

            agenda.push((i, True), v * self.fsa.ρ[i])

    def dijkstra_fwd(self, I=None):
        """Dijkstra's algorithm without early stopping."""

        assert self.fsa.R.superior

        # initialization
        α = self.R.chart()
        agenda = PriorityQueue(R=self.fsa.R)
        popped = set([])

        # base case
        if I is None:
            for q, w in self.fsa.I:
                agenda.push(q, w)
        else:
            for q in I:
                agenda.push(q, self.R.one)

        # main loop
        while agenda:
            i, v = agenda.pop()
            popped.add(i)
            α[i] += v

            for _, j, w in self.fsa.arcs(i):
                if j not in popped:
                    agenda.push(j, v * w)

        return α

    def _gauss_jordan(self):
        """
        Algorithm 4 from https://link.springer.com/content/pdf/10.1007%2F978-0-387-75450-5.pdf
        """

        # initialization
        last = self.W.copy()
        A = self.R.zeros(self.N, self.N)

        # basic iterations
        for k in range(self.N):
            A[k, k] = last[k, k].star()
            for i in range(self.N):
                for j in range(self.N):
                    if i != k or j != k:
                        A[i, j] = last[i, j] + last[i, k] * A[k, k] * last[k, j]
            last = A.copy()
            A = self.R.zeros(self.N, self.N)

        for k in range(self.N):
            A[k, k] += self.R.one

        return A

    def _lehmann(self, zero=True):
        """
        Lehmann's (1977) algorithm.
        """

        # initialization
        V = self.W.copy()
        U = self.W.copy()

        # basic iteration
        for j in range(self.N):
            V, U = U, V
            V = self.R.zeros(self.N, self.N)
            for i in range(self.N):
                for k in range(self.N):
                    # i ➙ j ⇝ j ➙ k
                    V[i, k] = U[i, k] + U[i, j] * U[j, j].star() * U[j, k]

        # post-processing (paths of length zero)
        if zero:
            for i in range(self.N):
                V[i, i] += self.R.one

        return V

    def lehmann(self, zero=True):
        # TODO: check we if we can't do away with this method.

        V = self._lehmann(zero=zero)

        W = {}
        for p in self.fsa.Q:
            for q in self.fsa.Q:
                if p in self.I and q in self.I:
                    W[p, q] = V[self.I[p], self.I[q]]
                elif p == q and zero:
                    W[p, q] = self.R.one
                else:
                    W[p, q] = self.R.zero

        return frozendict(W)

    def lehmann_pathsum(self):
        return self.allpairs_pathsum(self.lehmann())

    def lehmann_fwd(self):
        return self.allpairs_fwd(self.lehmann())

    def lehmann_bwd(self):
        return self.allpairs_bwd(self.lehmann())

    def decomposed_lehmann_pathsum(self):
        from rayuela.fsa.scc import SCC

        sccs = SCC(self.fsa)

        # compute the forward values in a decomposed way
        # they are identical to the forward values in the full FSA
        αs = {}
        for scc in sccs.scc():
            α = Pathsum(sccs.to_fsa(scc, αs)).forward(Strategy.LEHMANN)
            for i in scc:
                αs[i] = α[i]

        # compute the actual pathsum
        return reduce(lambda x, y: x + y, [αs[i] * w for i, w in self.fsa.F])

    def bellmanford_pathsum(self):
        pathsum = self.R.zero
        𝜷 = self.bellmanford_bwd()
        for q in self.fsa.Q:
            pathsum += self.fsa.λ[q] * 𝜷[q]
        return pathsum

    def bellmanford_fwd(self):

        # initialization
        α = self.R.chart()
        for q in self.fsa.Q:
            α[q] = self.fsa.λ[q]

        # main loop
        for _ in range(self.fsa.num_states):
            for i in self.fsa.Q:
                for _, j, w in self.fsa.arcs(i):
                    α[j] += α[i] * w

        return frozendict(α)

    def bellmanford_bwd(self):

        # initialization
        𝜷 = self.R.chart()
        for q in self.fsa.Q:
            𝜷[q] = self.fsa.ρ[q]

        # main loop
        for _ in range(self.fsa.num_states):
            for i in self.fsa.Q:
                for _, j, w in self.fsa.arcs(i):
                    𝜷[i] += 𝜷[j] * w

        return frozendict(𝜷)

    def johnson(self):
        from rayuela.fsa.transformer import Transformer

        𝜷 = self.fsa.backward(Strategy.BELLMANFORD)
        pfsa = self.fsa.push()
        pathsum = Pathsum(pfsa)

        W = self.fsa.R.chart()
        for p in pfsa.Q:
            α = pathsum.dijkstra_fwd([p])
            for q, w in α.items():
                W[p, q] = 𝜷[p] * w * ~𝜷[q]

        return W

    def johnson_pathsum(self):
        return self.allpairs_pathsum(self.johnson())

    def johnson_fwd(self):
        return self.allpairs_fwd(self.johnson())

    def johnson_bwd(self):
        return self.allpairs_bwd(self.johnson())

    def _iterate(self, K):
        P = self.R.diag(self.N)
        for n in range(K):
            P += self.W @ P
        return P

    def _fixpoint(self, K=200):
        if self.fsa.R.idempotent:
            return self._iterate(self.fsa.num_states)

        diag = self.R.diag(self.fsa.num_states)
        P_old = diag

        # TODO: add an approximate stopping criterion

        # fixed point iteration
        # while True:
        for _ in range(K):
            P_new = diag + self.W @ P_old

            # if P_new == P_old:
            # 	return P_old
            P_old = P_new

        return P_old

    def fixpoint(self):

        P = self._fixpoint()
        W = {}

        for p in self.fsa.Q:
            for q in self.fsa.Q:
                if p in self.I and q in self.I:
                    W[p, q] = P[self.I[p], self.I[q]]
                elif p == q:
                    W[p, q] = self.R.one
                else:
                    W[p, q] = self.R.zero

        return frozendict(W)

    def fixpoint_pathsum(self):
        return self.allpairs_pathsum(self.fixpoint())

    def fixpoint_fwd(self):
        return self.allpairs_fwd(self.fixpoint())

    def fixpoint_bwd(self):
        return self.allpairs_bwd(self.fixpoint())

    def viterbi_φ_pathsum(self, strategy: Strategy):
        pathsum = self.R.zero
        β = self.backward(strategy)
        for q in self.fsa.Q:
            pathsum += self.fsa.λ[q] * β[q]
        return pathsum

    

    