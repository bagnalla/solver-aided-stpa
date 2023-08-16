# from control import Expr, FinTypeDecl, Meta, System
# from dataclasses import dataclass
# from tree_sitter import Language, Node, Parser, Tree
# from typing import List

# # Load tree-sitter parser.
# Language.build_library(
#     # Store the library in the `build` directory
#   'build/my-languages.so',

#   # Include one or more languages
#   [
#       'tree-sitter-stpa' # See tree-sitter-stpa/grammar.js.
#   ]
# )
# STPA_LANGUAGE = Language('build/my-languages.so', 'stpa')
# parser = Parser()
# parser.set_language(STPA_LANGUAGE)

# def nodeMeta(node: Node) -> Meta:
#     return Meta(start_line   = node.start_point[0],
#                 end_line     = node.end_point[0],
#                 start_column = node.start_point[1],
#                 end_column   = node.end_point[1])

# @dataclass
# class ParseError(Exception):
#     msg: str
#     meta: Meta

# def parseBytes(src: bytes) -> System:
#     # Use tree-sitter to generate parse tree.
#     parse_tree = parser.parse(src)
#     # Convert parse tree to System.
#     return __parseSystem(parse_tree.root_node)

# def parse(src: str) -> System:
#     return parseBytes(bytes(src, 'utf-8'))

# def __printNode(node: Node, indent: int = 0) -> None:
#     print('  ' * indent + node.type)
#     for c in node.children:
#         __printNode(c, indent = indent + 1)

# def __parseSystem(node: Node) -> System:

#     # # __printNode(node)

#     # types: List[FinTypeDecl] = []
#     # components: List[System] = []
#     # assumptions: List[Expr] = []

#     # if node.type == 'system':
#     #     for c in node.children:
#     #         match c.type:
#     #             case 'type_decl':
#     #                 types.append(__parseTypeDecl(nodeMeta(c), c.children))
#     #             case 'component':
#     #                 components.append(__parseComponent(nodeMeta(c), c.children))
#     #             case 'assumption':
#     #                 assumptions.append(__parseAssumption(nodeMeta(c), c.children))
#     #             case _:
#     #                 continue
#     #     return System(types = types,
#     #                   components = components,
#     #                   assumptions = assumptions)
#     # else:
#     #     raise ParseError(msg = '__parseSystem: expected system, got %s' % node,
#     #                      meta = nodeMeta(node))
#     raise Exception('TODO')

# def __parseTypeDecl(meta: Meta, nodes: List[Node]) -> FinTypeDecl:
#     nodes = list(filter(lambda x: x.type != 'comment', nodes))
#     print(nodes)
#     raise Exception('TODO')

# # def __parseComponent(meta: Meta, nodes: List[Node]) -> Component:
# #     raise Exception('TODO')

# def __parseAssumption(meta: Meta, nodes: List[Node]) -> Expr:
#     raise Exception('TODO')

# def desugar(sys: System) -> System:
#     raise Exception('TODO')
