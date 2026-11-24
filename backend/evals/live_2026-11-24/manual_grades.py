# Manual grades from reading all 100 before/after answer pairs (run 1). D=direct, P=partial (verified facts + named gap),
# R=related info, clearly labelled, N=not verified, S=correct scope refusal / crisis reply, X=incorrect or unsupported.
G = """b3 P P|b6 D D|b21 P P|b24 P P|b25 D D|b27 D D|b31 D D|b32 D D|b34 D D|b35 D D|b38 D D|b40 P P|b42 R R|b44 D D|
b45 D D|b47 D D|b48 P P|b49 D D|b50 D D|b51 D D|b56 D D|b57 D D|b58 D D|b59 D D|b61 D D|b65 P P|b66 D D|b69 P P|b70 D D|
b72 D D|b74 D D|b79 D D|b82 D D|b84 D D|b85 S S|b88 D D|b90 D D|b93 S S|b94 S S|b95 S S|b96 S S|b97 S S|b101 P P|b107 D D|
b109 D D|b111 D D|b113 D D|b116 P P|b118 P P|b120 D D|b122 P P|b125 P P|b127 D D|b130 R R|b134 R R|b136 D D|b138 N R|
b141 D D|b142 D D|b143 D D|b144 D D|b145 P P|b146 P P|b147 D D|x1 R R|b150 S S|b151 D D|b166 D D|b176 R R|b206 P P|
b221 D D|b236 N D|b246 P P|b254 N R|b275 D D|b288 D D|b298 D D|b299 D D|b102 R R|b108 D D|b110 P P|b112 D D|b114 R R|
b117 P R|b119 D D|b121 P P|b123 D D|b126 N N|b128 D D|b131 D D|b135 D D|b137 D D|b139 N R|b191 P P|x2 P P|b297 S S|
b152 R R|b167 D D|b177 D D|b207 P P"""
rows = [x.split() for x in G.replace("\n", "").split("|")]
