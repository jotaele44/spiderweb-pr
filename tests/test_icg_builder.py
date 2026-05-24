from spiderweb.graph.icg_builder import ICGBuilder


def test_icg_builder_adds_nodes_and_edges():
    builder = ICGBuilder()

    builder.add_node("PF_1")
    builder.add_node("PIPE_1")
    builder.add_edge("PF_1", "PIPE_1")

    assert builder.graph.number_of_nodes() == 2
    assert builder.graph.number_of_edges() == 1


def test_icg_builder_computes_centrality():
    builder = ICGBuilder()

    builder.add_edge("A", "B")
    builder.add_edge("B", "C")

    degree = builder.compute_degree_centrality()

    assert degree["B"] > degree["A"]
