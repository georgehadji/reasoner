import ast

code = "f" + chr(34) + chr(123) + "1+1" + chr(125) + chr(34)
print(repr(code))
tree = ast.parse(code, mode="eval")
print(ast.dump(tree, indent=2))
