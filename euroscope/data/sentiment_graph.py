"""
Sentiment Knowledge Graph

Maps relationships between macroeconomic entities (e.g., ECB, USD, Inflation)
based on incoming news articles to track long-term narratives.
"""

import logging
import json
import os
import networkx as nx
from typing import List, Dict, Tuple

logger = logging.getLogger("euroscope.data.sentiment_graph")

class NarrativeGraph:
    def __init__(self, persist_dir: str = "data"):
        self.persist_dir = persist_dir
        self.graph_file = os.path.join(self.persist_dir, "sentiment_graph.graphml")
        self.graph = nx.DiGraph()
        self._load_graph()

    def _load_graph(self):
        try:
            if os.path.exists(self.graph_file):
                self.graph = nx.read_graphml(self.graph_file)
                logger.info(f"Loaded Narrative Graph with {self.graph.number_of_nodes()} nodes.")
        except Exception as e:
            logger.error(f"Failed to load Narrative Graph: {e}")
            self.graph = nx.DiGraph()

    def _save_graph(self):
        try:
            os.makedirs(self.persist_dir, exist_ok=True)
            nx.write_graphml(self.graph, self.graph_file)
        except Exception as e:
            logger.error(f"Failed to save Narrative Graph: {e}")

    def update_from_news(self, raw_relations: List[Dict]):
        """
        Updates the graph with new relations.
        Format of raw_relations: [{"source": "ECB", "target": "Rates", "relation": "increases", "weight": 1.0}]
        """
        for rel in raw_relations:
            src_raw = rel.get("source")
            tgt_raw = rel.get("target")
            edge_type = rel.get("relation", "affects")
            w = float(rel.get("weight", 1.0))
            
            if not src_raw or not tgt_raw:
                continue
                
            src = src_raw.strip().upper()
            tgt = tgt_raw.strip().upper()

            # Add nodes
            if not self.graph.has_node(src): self.graph.add_node(src, weight=1.0)
            if not self.graph.has_node(tgt): self.graph.add_node(tgt, weight=1.0)

            # Add or update edge
            if self.graph.has_edge(src, tgt):
                current_weight = self.graph[src][tgt].get("weight", 1.0)
                # Exponential decay of old relations compared to new ones, or just additive
                self.graph[src][tgt]["weight"] = current_weight + w
                self.graph[src][tgt]["label"] = edge_type
            else:
                self.graph.add_edge(src, tgt, weight=w, label=edge_type)
        
        self._prune_graph()
        self._save_graph()

    def _prune_graph(self, max_nodes=100):
        """Keep the graph from growing infinitely by removing weakest nodes."""
        if self.graph.number_of_nodes() <= max_nodes:
            return
            
        # Calculate centrality
        centrality = nx.degree_centrality(self.graph)
        
        # Sort nodes by centrality
        sorted_nodes = sorted(centrality.items(), key=lambda x: x[1])
        nodes_to_remove = [n[0] for n in sorted_nodes[:self.graph.number_of_nodes() - max_nodes]]
        
        self.graph.remove_nodes_from(nodes_to_remove)

    def get_central_narratives(self, top_n: int = 5) -> str:
        """Returns the most central nodes and their primary outgoing edges."""
        if self.graph.number_of_nodes() == 0:
            return "No established narratives."

        try:
            # Degree centrality includes both in and out degree
            centrality = nx.degree_centrality(self.graph)
            sorted_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:top_n]
            
            narratives = []
            for node, score in sorted_nodes:
                edges = self.graph.out_edges(node, data=True)
                if not edges:
                    continue
                # Get the strongest edge
                strongest = max(edges, key=lambda x: x[2].get('weight', 0))
                target = strongest[1]
                relation = strongest[2].get('label', 'affects')
                
                narratives.append(f"• {node} ➔ {relation} ➔ {target}")
                
            if not narratives:
                return "Graph building..."
            return "Current Market Engine Narratives:\n" + "\n".join(narratives)
        except Exception as e:
            logger.error(f"Failed to generate narrative summary: {e}")
            return "Narrative generation error."
