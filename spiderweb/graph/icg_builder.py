import networkx as nx


class ICGBuilder:
    def __init__(self):
        self.graph = nx.Graph()

    def add_node(self, node_id: str, **attrs):
        self.graph.add_node(node_id, **attrs)

    def add_edge(self, from_node: str, to_node: str, **attrs):
        self.graph.add_edge(from_node, to_node, **attrs)

    def compute_degree_centrality(self):
        return nx.degree_centrality(self.graph)

    def compute_betweenness_centrality(self):
        return nx.betweenness_centrality(self.graph)
