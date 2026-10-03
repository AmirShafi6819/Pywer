import os
import shutil
import tempfile
import unittest
from pathlib import Path

from pywer import config


class TestPropertiesParser(unittest.TestCase):
    def test_key_value_pairs(self):
        parsed = config.parse_properties("server-port=19140\nmotd=Hello\n")
        self.assertEqual(parsed, {"server-port": "19140", "motd": "Hello"})

    def test_keys_are_lowercased_and_values_kept(self):
        self.assertEqual(config.parse_properties("MotD=MiXeD Case"), {"motd": "MiXeD Case"})

    def test_comments_are_skipped(self):
        parsed = config.parse_properties("# a comment\n! another\ngamemode=1\n   \n")
        self.assertEqual(parsed, {"gamemode": "1"})

    def test_hash_inside_value_is_kept(self):
        self.assertEqual(config.parse_properties("motd=Server #1"), {"motd": "Server #1"})

    def test_colon_separator(self):
        self.assertEqual(config.parse_properties("motd: Hello"), {"motd": "Hello"})

    def test_empty_value(self):
        self.assertEqual(config.parse_properties("motd=\n"), {"motd": ""})

    def test_line_continuation(self):
        parsed = config.parse_properties("motd=a \\\nb\n")
        self.assertEqual(parsed, {"motd": "a b"})

    def test_line_without_separator_warns_but_does_not_raise(self):
        config._WARNINGS.clear()
        self.assertEqual(config.parse_properties("garbage line\n"), {})
        self.assertEqual(len(config._WARNINGS), 1)
        config._WARNINGS.clear()


class TestYamlParser(unittest.TestCase):
    def test_flat_mapping(self):
        self.assertEqual(config.parse_yaml("a: 1\nb: two\n"), {"a": 1, "b": "two"})

    def test_nested_mapping(self):
        parsed = config.parse_yaml("world:\n  min-y: -64\n  max-y: 319\n")
        self.assertEqual(parsed, {"world": {"min-y": -64, "max-y": 319}})

    def test_scalars(self):
        parsed = config.parse_yaml(
            "i: 42\nh: 0x10\nf: 0.5\nt: true\nf2: no\nn: null\ntilde: ~\nempty:\n"
            "q: 'quoted: value'\ndq: \"double\"\nplain: hello world\nver: 1.21.50\n"
        )
        self.assertEqual(parsed, {
            "i": 42, "h": 16, "f": 0.5, "t": True, "f2": False, "n": None, "tilde": None,
            "empty": None, "q": "quoted: value", "dq": "double", "plain": "hello world",
            "ver": "1.21.50",
        })

    def test_one_and_zero_stay_numbers(self):
        # YAML 1.2 does not treat 1/0 as booleans, unlike a properties file.
        self.assertEqual(config.parse_yaml("a: 1\nb: 0\n"), {"a": 1, "b": 0})

    def test_block_list(self):
        parsed = config.parse_yaml("keys:\n  - a\n  - b\nother: 1\n")
        self.assertEqual(parsed, {"keys": ["a", "b"], "other": 1})

    def test_inline_list(self):
        self.assertEqual(config.parse_yaml("keys: [1, 2]"), {"keys": [1, 2]})
        self.assertEqual(config.parse_yaml("keys: []"), {"keys": []})

    def test_comments_and_blank_lines(self):
        parsed = config.parse_yaml("# header\n\na: 1  # trailing\nb: '# not a comment'\n")
        self.assertEqual(parsed, {"a": 1, "b": "# not a comment"})

    def test_deep_nesting_and_sibling_after_nested(self):
        parsed = config.parse_yaml("a:\n  b:\n    c: 1\nd: 2\n")
        self.assertEqual(parsed, {"a": {"b": {"c": 1}}, "d": 2})

    def test_malformed_lines_raise(self):
        for text in ("no separator here\n", "a: 1\n- orphan\n", "- orphan\n"):
            with self.assertRaises(ValueError):
                config.parse_yaml(text)


class TestCoercion(unittest.TestCase):
    def test_int_kinds(self):
        self.assertEqual(config._coerce("int", "42", "f", "k"), 42)
        self.assertEqual(config._coerce("int", " 0x10 ", "f", "k"), 16)
        self.assertEqual(config._coerce("int", "08", "f", "k"), 8)
        self.assertEqual(config._coerce("int", -5, "f", "k"), -5)

    def test_bool_kinds(self):
        for text in ("1", "true", "YES", "on"):
            self.assertIs(config._coerce("bool", text, "f", "k"), True, text)
        for text in ("0", "false", "No", "off"):
            self.assertIs(config._coerce("bool", text, "f", "k"), False, text)

    def test_optbool_accepts_null(self):
        for text in ("null", "", "none", "~"):
            self.assertIsNone(config._coerce("optbool", text, "f", "k"), text)
        self.assertIs(config._coerce("optbool", "true", "f", "k"), True)
        self.assertIs(config._coerce("optbool", "0", "f", "k"), False)

    def test_float_and_str(self):
        self.assertEqual(config._coerce("float", "0.5", "f", "k"), 0.5)
        self.assertEqual(config._coerce("str", "anything", "f", "k"), "anything")

    def test_bad_values_raise_with_context(self):
        with self.assertRaises(ValueError) as ctx:
            config._coerce("int", "abc", "server.properties", "max-players")
        self.assertIn("server.properties", str(ctx.exception))
        self.assertIn("max-players", str(ctx.exception))

    def test_list_where_scalar_expected_raises(self):
        with self.assertRaises(ValueError):
            config._coerce("int", [1, 2], "pywer.yml", "world:biome")


class TestTemplates(unittest.TestCase):
    def test_generated_properties_round_trip(self):
        parsed = config.parse_properties(config.render_properties())
        for target, kind, key, default, _doc, _section in config.SIMPLE:
            self.assertIn(key.lower(), parsed, "server.properties is missing %s" % key)
            if target.startswith("SPAWN_"):
                continue
            self.assertEqual(config._coerce(kind, parsed[key.lower()], "f", key), default, key)

    def test_generated_yaml_round_trip(self):
        parsed = config.parse_yaml(config.render_yaml())
        for target, kind, key, default, _doc, section in config.ADVANCED:
            node = parsed.get(section)
            self.assertIsInstance(node, dict, "pywer.yml is missing section %s" % section)
            self.assertIn(key, node, "pywer.yml is missing %s:%s" % (section, key))
            self.assertEqual(config._coerce(kind, node[key], "f", key), default, "%s:%s" % (section, key))

    def test_every_default_is_documented(self):
        for target, _kind, _key, _default, doc, _section in config._OPTIONS:
            self.assertTrue(doc.strip(), "%s has no help text" % target)

    def test_option_keys_are_unique(self):
        seen = set()
        for _target, _kind, key, _default, _doc, section in config.ADVANCED:
            self.assertNotIn((section, key), seen, "duplicate pywer.yml key %s:%s" % (section, key))
            seen.add((section, key))


class TestLoading(unittest.TestCase):
    """Loading has to work against a real directory, so each test gets a throwaway one."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.previous_cwd = os.getcwd()
        self.previous_env = os.environ.get(config.ENV_DIR)
        os.chdir(self.directory)
        os.environ[config.ENV_DIR] = str(self.directory)

    def tearDown(self):
        os.chdir(self.previous_cwd)
        if self.previous_env is None:
            os.environ.pop(config.ENV_DIR, None)
        else:
            os.environ[config.ENV_DIR] = self.previous_env
        shutil.rmtree(self.directory, ignore_errors=True)
        config.reload()

    def write(self, name, text):
        (self.directory / name).write_text(text, encoding="utf-8")

    def test_files_are_created_with_defaults(self):
        config.load()
        config._publish()
        self.assertTrue((self.directory / config.PROPERTIES_FILE).is_file())
        self.assertTrue((self.directory / config.YAML_FILE).is_file())
        self.assertEqual(config.PORT, 19132)
        self.assertEqual(config.DEFAULT_SPAWN, (0, 100, 0))

    def test_existing_files_are_not_overwritten(self):
        self.write(config.PROPERTIES_FILE, "server-port=25565\n")
        config.load()
        config._publish()
        self.assertEqual(config.PORT, 25565)
        self.assertIn("server-port=25565", (self.directory / config.PROPERTIES_FILE).read_text())

    def test_properties_overrides_apply(self):
        self.write(config.PROPERTIES_FILE, "\n".join([
            "server-port=25565", "server-ip=127.0.0.1", "motd=My World", "max-players=32",
            "gamemode=1", "level-seed=99", "view-distance=8",
            "spawn-x=1", "spawn-y=64", "spawn-z=-2",
        ]))
        config.load()
        config._publish()
        self.assertEqual(config.PORT, 25565)
        self.assertEqual(config.BIND, "127.0.0.1")
        self.assertEqual(config.SERVER_TITLE, "My World")
        self.assertEqual(config.MAX_PLAYERS, 32)
        self.assertEqual(config.GAMEMODE, 1)
        self.assertEqual(config.SEED, 99)
        self.assertEqual(config.MAX_RADIUS, 8)
        self.assertEqual(config.DEFAULT_SPAWN, (1, 64, -2))

    def test_yaml_overrides_apply(self):
        self.write(config.YAML_FILE, "\n".join([
            "network:", "  encryption: false", "  compression-threshold: 512",
            "proxy:", "  mode: true", "  encryption: false",
            "world:", "  min-y: 0", "  max-y: 255", "  trees: no", "  biome: 2",
            "debug:", "  packets: yes", "  connection: on",
            "gameplay:", "  break-input-timeout: 1.5",
        ]))
        config.load()
        config._publish()
        self.assertIs(config.ENCRYPTION, False)
        self.assertEqual(config.COMPRESSION_THRESHOLD, 512)
        self.assertIs(config.PROXY_MODE, True)
        self.assertIs(config.PROXY_ENCRYPTION, False)
        self.assertEqual(config.MIN_Y, 0)
        self.assertEqual(config.MAX_Y, 255)
        self.assertIs(config.TREES, False)
        self.assertEqual(config.PLAINS_BIOME, 2)
        self.assertIs(config.DEBUG_PACKETS, True)
        self.assertIs(config.DEBUG, True)
        self.assertEqual(config.BREAK_INPUT_TIMEOUT, 1.5)

    def test_properties_win_over_yaml(self):
        self.write(config.PROPERTIES_FILE, "server-port=25565\n")
        self.write(config.YAML_FILE, "protocol:\n  version: 800\n")
        config.load()
        config._publish()
        self.assertEqual(config.PORT, 25565)
        self.assertEqual(config.PROTOCOL, 800)

    def test_explicit_null_is_not_treated_as_missing(self):
        self.write(config.YAML_FILE, "proxy:\n  encryption: null\n")
        self.assertIsNone(config._dig(config.parse_yaml("proxy:\n  encryption: null\n"), "proxy", "encryption"))
        self.assertIs(config._dig(config.parse_yaml("proxy:\n  mode: true\n"), "proxy", "encryption"),
                      config._MISSING)

    def test_missing_keys_keep_the_default(self):
        self.write(config.PROPERTIES_FILE, "server-port=25565\n")
        config.load()
        config._publish()
        self.assertEqual(config.PORT, 25565)
        self.assertEqual(config.MAX_PLAYERS, config.DEFAULTS["MAX_PLAYERS"])

    def test_bad_value_keeps_the_default_and_warns(self):
        self.write(config.PROPERTIES_FILE, "max-players=lots\n")
        config._WARNINGS.clear()
        config.load()
        self.assertEqual(len(config._WARNINGS), 1)
        self.assertIn("max-players", config._WARNINGS[0])
        config._publish()  # drains the warnings and prints them
        self.assertEqual(config.MAX_PLAYERS, 8)

    def test_broken_yaml_keeps_every_default(self):
        self.write(config.YAML_FILE, "network:\n  this line is broken\n")
        config._WARNINGS.clear()
        config.load()
        self.assertEqual(len(config._WARNINGS), 1)
        config._publish()
        self.assertEqual(config.COMPRESSION_THRESHOLD, 256)

    def test_wrong_type_for_a_section_does_not_crash(self):
        self.write(config.YAML_FILE, "world: not-a-section\n")
        config._WARNINGS.clear()
        config.load()
        config._publish()
        self.assertEqual(config.SEA_LEVEL, 62)
        config._WARNINGS.clear()

    def test_reload_picks_up_edits(self):
        self.write(config.PROPERTIES_FILE, "server-port=1\n")
        config.load()
        config._publish()
        self.assertEqual(config.PORT, 1)
        self.write(config.PROPERTIES_FILE, "server-port=2\n")
        config.reload()
        self.assertEqual(config.PORT, 2)

    def test_as_dict_covers_every_option(self):
        values = config.as_dict()
        for target, _kind, _key, _default, _doc, _section in config._OPTIONS:
            self.assertIn(target, values)
        self.assertEqual(len(values), len(config._OPTIONS))


if __name__ == "__main__":
    unittest.main()
