import ast
import unittest
from collections import defaultdict
from pathlib import Path


class api_routes(unittest.TestCase):
    def test_api_route_methods_are_unique(self):
        source = Path('frontend/api.py')
        module = ast.parse(source.read_text(), filename=str(source))
        routes = defaultdict(list)

        for node in module.body:
            if not isinstance(node, ast.FunctionDef):
                continue

            for decorator in node.decorator_list:
                if not (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr == 'route'
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == 'api'
                    and decorator.args
                ):
                    continue

                route = ast.literal_eval(decorator.args[0])
                methods = ('GET',)
                for keyword in decorator.keywords:
                    if keyword.arg == 'methods':
                        methods = tuple(ast.literal_eval(keyword.value))

                for method in methods:
                    routes[(route, method)].append((node.name, node.lineno))

        duplicates = {
            key: values
            for key, values in routes.items()
            if len(values) > 1
        }
        self.assertEqual({}, duplicates)


if __name__ == '__main__':
    unittest.main()
