import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass


def load_sql_retriever():
    for name in [
        "app",
        "app.llm",
        "app.llm.client",
        "app.core",
        "app.core.db",
        "app.core.logger",
        "app.retrievers",
        "app.retrievers.sql_retriever",
    ]:
        sys.modules.pop(name, None)

    app = types.ModuleType("app")
    app.__path__ = [str(ROOT / "app")]
    sys.modules["app"] = app

    retrievers = types.ModuleType("app.retrievers")
    retrievers.__path__ = [str(ROOT / "app" / "retrievers")]
    sys.modules["app.retrievers"] = retrievers

    llm_pkg = types.ModuleType("app.llm")
    llm_pkg.__path__ = [str(ROOT / "app" / "llm")]
    sys.modules["app.llm"] = llm_pkg

    client = types.ModuleType("app.llm.client")
    client.ask_llm = lambda *args, **kwargs: ""
    client.ask_sql_planner = lambda *args, **kwargs: ""
    sys.modules["app.llm.client"] = client

    core_pkg = types.ModuleType("app.core")
    core_pkg.__path__ = [str(ROOT / "app" / "core")]
    sys.modules["app.core"] = core_pkg

    db = types.ModuleType("app.core.db")
    db.run_query = lambda sql, params=None: []
    sys.modules["app.core.db"] = db

    logger_mod = types.ModuleType("app.core.logger")
    logger_mod.get_logger = lambda name: DummyLogger()
    sys.modules["app.core.logger"] = logger_mod

    spec = importlib.util.spec_from_file_location(
        "app.retrievers.sql_retriever",
        ROOT / "app" / "retrievers" / "sql_retriever.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ResidentSuperlativeTests(unittest.TestCase):
    def setUp(self):
        self.sql_retriever = load_sql_retriever()

    def test_implicit_oldest_uses_age_ranking(self):
        plan = self.sql_retriever._detect_resident_aggregate_plan("who is the oldest?")

        self.assertIsNotNone(plan)
        self.assertEqual(plan["_macro"], "resident_age_ranking")
        self.assertEqual(plan["_rank_type"], "oldest")
        self.assertEqual(plan["order_direction"], "DESC")

    def test_implicit_youngest_uses_age_ranking(self):
        plan = self.sql_retriever._detect_resident_aggregate_plan("youngest?")

        self.assertIsNotNone(plan)
        self.assertEqual(plan["_macro"], "resident_age_ranking")
        self.assertEqual(plan["_rank_type"], "youngest")
        self.assertEqual(plan["order_direction"], "ASC")

    def test_oldest_is_not_extracted_as_resident_name(self):
        self.assertIsNone(self.sql_retriever._extract_resident_name("who is the oldest?"))

    def test_handle_sql_answers_oldest_from_age_ranking(self):
        self.sql_retriever.run_query = lambda sql, params=None: [("John Mathew", 79)]

        response = self.sql_retriever.handle_sql("who is the oldest?", community_id=1)

        self.assertEqual(response["answer"], "The oldest resident is John Mathew, age 79.")
        self.assertEqual(response["plan"]["_rank_type"], "oldest")


if __name__ == "__main__":
    unittest.main()
