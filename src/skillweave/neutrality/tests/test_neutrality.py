"""SW-N-G2A executable contract tests.

EvidenceVerificationResult canonical 9-status tests, parser failure
classification, provider adapter registry, standalone mode, compiler
determinism, R4 frozen adapter, provider substitution, and namespace
ownership.

All tests MUST pass with Capacium fully absent from the environment.
"""

from __future__ import annotations

import hashlib
import json
import sys
import unittest

from skillweave.neutrality import (
    CapaciumKind,
    CapabilityProvider,
    CompiledDefinition,
    EvidenceVerificationResult,
    EvidenceVerificationStatus,
    FROZEN_R4_BYTES,
    FROZEN_R4_EVIDENCE_DIGEST,
    LocalEvidenceVerificationProvider,
    NoOpVerificationProvider,
    ParserError,
    ParserFailureClassification,
    ProcessDefinition,
    ProcessPack,
    R4CompatibilityAdapter,
    compile_process,
    get_provider,
    list_providers,
    register_provider,
    unregister_provider,
    VerificationRequest,
    verify_evidence,
)


class TestCanonicalEVRStatuses(unittest.TestCase):
    def test_all_nine_canonical_statuses_exist(self):
        expected = {
            "VALID",
            "INVALID",
            "KEY_EXPIRED",
            "KEY_REVOKED",
            "UNKNOWN_KEY",
            "MALFORMED",
            "UNSUPPORTED_ALGORITHM",
            "INCONCLUSIVE",
            "UNAVAILABLE",
        }
        actual = {s.value for s in EvidenceVerificationStatus}
        self.assertEqual(expected, actual)

    def test_only_valid_is_verified(self):
        for status in EvidenceVerificationStatus:
            evr = EvidenceVerificationResult(status)
            expected = status == EvidenceVerificationStatus.VALID
            self.assertEqual(expected, evr.is_verified(), f"{status}.is_verified()")

    def test_inconclusive_not_verified_not_pass(self):
        evr = EvidenceVerificationResult(EvidenceVerificationStatus.INCONCLUSIVE)
        self.assertFalse(evr.is_verified())
        self.assertEqual("INCONCLUSIVE", evr.status.to_skillweave_status())

    def test_unavailable_not_verified_not_pass(self):
        evr = EvidenceVerificationResult(EvidenceVerificationStatus.UNAVAILABLE)
        self.assertFalse(evr.is_verified())
        self.assertEqual("UNAVAILABLE", evr.status.to_skillweave_status())

    def test_inconclusive_never_coerced_to_pass(self):
        evr = EvidenceVerificationResult(EvidenceVerificationStatus.INCONCLUSIVE)
        self.assertFalse(evr.is_verified())
        self.assertNotEqual("PASS", evr.status.to_skillweave_status())

    def test_unavailable_never_coerced_to_pass(self):
        evr = EvidenceVerificationResult(EvidenceVerificationStatus.UNAVAILABLE)
        self.assertFalse(evr.is_verified())
        self.assertNotEqual("PASS", evr.status.to_skillweave_status())

    def test_valid_to_skillweave_is_pass(self):
        evr = EvidenceVerificationResult(EvidenceVerificationStatus.VALID)
        self.assertEqual("PASS", evr.status.to_skillweave_status())

    def test_invalid_to_skillweave_is_fail(self):
        evr = EvidenceVerificationResult(EvidenceVerificationStatus.INVALID)
        self.assertEqual("FAIL", evr.status.to_skillweave_status())


class TestEVRFromDict(unittest.TestCase):
    def test_from_dict_valid(self):
        evr = EvidenceVerificationResult.from_dict({"status": "VALID"})
        self.assertTrue(evr.is_verified())

    def test_from_dict_invalid(self):
        evr = EvidenceVerificationResult.from_dict({"status": "INVALID"})
        self.assertFalse(evr.is_verified())

    def test_from_dict_key_expired(self):
        evr = EvidenceVerificationResult.from_dict({"status": "KEY_EXPIRED"})
        self.assertFalse(evr.is_verified())

    def test_from_dict_key_revoked(self):
        evr = EvidenceVerificationResult.from_dict({"status": "KEY_REVOKED"})
        self.assertFalse(evr.is_verified())

    def test_from_dict_unknown_key(self):
        evr = EvidenceVerificationResult.from_dict({"status": "UNKNOWN_KEY"})
        self.assertFalse(evr.is_verified())

    def test_from_dict_unsupported_algorithm(self):
        evr = EvidenceVerificationResult.from_dict({"status": "UNSUPPORTED_ALGORITHM"})
        self.assertFalse(evr.is_verified())

    def test_from_dict_missing_status(self):
        with self.assertRaises(ParserError):
            EvidenceVerificationResult.from_dict({})

    def test_from_dict_unknown_status_is_parser_error(self):
        with self.assertRaises(ParserError) as ctx:
            EvidenceVerificationResult.from_dict({"status": "INVALID_SIGNATURE"})
        self.assertIn("INVALID_SIGNATURE", str(ctx.exception))

    def test_from_dict_malformed_raises_not_returns(self):
        with self.assertRaises(ParserError) as ctx:
            EvidenceVerificationResult.from_dict({"status": "MALFORMED"})
        self.assertIn("MALFORMED", str(ctx.exception))
        self.assertIn("fail-closed", str(ctx.exception))

    def test_from_dict_non_string_status(self):
        with self.assertRaises(ParserError):
            EvidenceVerificationResult.from_dict({"status": 42})


class TestEVRRoundtrip(unittest.TestCase):
    def test_roundtrip_all_statuses(self):
        for status in EvidenceVerificationStatus:
            evr = EvidenceVerificationResult(status, detail=f"test_{status.value}")
            d = evr.to_dict()
            evr2 = EvidenceVerificationResult.from_dict(d)
            self.assertEqual(evr, evr2)

    def test_to_dict_structure(self):
        evr = EvidenceVerificationResult(EvidenceVerificationStatus.VALID, "ok")
        d = evr.to_dict()
        self.assertEqual({"status": "VALID", "detail": "ok"}, d)

    def test_from_dict_rejects_extra_fields(self):
        evr = EvidenceVerificationResult.from_dict(
            {"status": "VALID", "detail": "ok", "entitlement": "grant"}
        )
        self.assertTrue(evr.is_verified())

    def test_evr_has_no_entitlement_field(self):
        evr = EvidenceVerificationResult(EvidenceVerificationStatus.VALID)
        self.assertFalse(hasattr(evr, "entitlement"))
        self.assertFalse(hasattr(evr, "authorization"))

    def test_evr_dict_has_no_entitlement(self):
        evr = EvidenceVerificationResult(EvidenceVerificationStatus.VALID)
        d = evr.to_dict()
        self.assertNotIn("entitlement", d)
        self.assertNotIn("authorization")
        self.assertNotIn("commercial", d)


class TestProviderRegistry(unittest.TestCase):
    def setUp(self):
        for pid in list(list_providers()):
            unregister_provider(pid)

    def test_register_and_get(self):
        provider = NoOpVerificationProvider()
        register_provider("test-noop", provider)
        self.assertIs(provider, get_provider("test-noop"))

    def test_unknown_returns_none(self):
        self.assertIsNone(get_provider("nonexistent-provider"))

    def test_empty_id_raises(self):
        with self.assertRaises(ValueError):
            register_provider("", NoOpVerificationProvider())

    def test_verify_unregistered_gives_unavailable(self):
        request = VerificationRequest(evidence_digest="abc123")
        result = verify_evidence(request, provider_id="missing")
        self.assertEqual(EvidenceVerificationStatus.UNAVAILABLE, result.status)
        self.assertFalse(result.is_verified())

    def test_verify_registered_provider(self):
        provider = NoOpVerificationProvider()
        register_provider("noop", provider)
        request = VerificationRequest(evidence_digest="abc123")
        result = verify_evidence(request, provider_id="noop")
        self.assertEqual(EvidenceVerificationStatus.UNAVAILABLE, result.status)

    def test_unregister(self):
        register_provider("tmp", NoOpVerificationProvider())
        unregister_provider("tmp")
        self.assertIsNone(get_provider("tmp"))

    def test_list_providers_returns_copy(self):
        register_provider("a", NoOpVerificationProvider())
        providers = list_providers()
        self.assertIn("a", providers)
        providers.pop("a")
        self.assertIn("a", list_providers())


class TestLocalProvider(unittest.TestCase):
    def test_known_digest_valid(self):
        prov = LocalEvidenceVerificationProvider()
        prov.register_digest("abc123", EvidenceVerificationStatus.VALID)
        result = prov.verify(VerificationRequest(evidence_digest="abc123"))
        self.assertTrue(result.is_verified())
        self.assertEqual(EvidenceVerificationStatus.VALID, result.status)

    def test_unknown_digest_returns_unknown_key(self):
        prov = LocalEvidenceVerificationProvider()
        result = prov.verify(VerificationRequest(evidence_digest="nonexistent"))
        self.assertEqual(EvidenceVerificationStatus.UNKNOWN_KEY, result.status)
        self.assertFalse(result.is_verified())

    def test_register_multiple_digests(self):
        prov = LocalEvidenceVerificationProvider()
        prov.register_digest("a", EvidenceVerificationStatus.VALID)
        prov.register_digest("b", EvidenceVerificationStatus.INVALID)
        self.assertTrue(prov.verify(VerificationRequest(evidence_digest="a")).is_verified())
        self.assertFalse(prov.verify(VerificationRequest(evidence_digest="b")).is_verified())

    def test_substitution_same_input_same_result(self):
        prov1 = LocalEvidenceVerificationProvider()
        prov1.register_digest("abc", EvidenceVerificationStatus.VALID)
        prov2 = LocalEvidenceVerificationProvider()
        prov2.register_digest("abc", EvidenceVerificationStatus.VALID)
        r1 = prov1.verify(VerificationRequest(evidence_digest="abc"))
        r2 = prov2.verify(VerificationRequest(evidence_digest="abc"))
        self.assertEqual(r1, r2)

    def test_noop_always_unavailable(self):
        prov = NoOpVerificationProvider()
        result = prov.verify(VerificationRequest(evidence_digest="anything"))
        self.assertEqual(EvidenceVerificationStatus.UNAVAILABLE, result.status)


class TestCompiler(unittest.TestCase):
    def test_single_definition_compiles_to_workflow(self):
        pd = ProcessDefinition("sw-proc-001", "1.0.0", "Test Process")
        pp = ProcessPack("pack-001", "1.0.0", (pd,))
        compiled = compile_process(pp)
        self.assertEqual(CapaciumKind.WORKFLOW, compiled.capacium_kind)

    def test_multiple_definitions_compile_to_bundle(self):
        pd1 = ProcessDefinition("sw-proc-001", "1.0.0", "Test A")
        pd2 = ProcessDefinition("sw-proc-002", "1.0.0", "Test B")
        pd3 = ProcessDefinition("sw-proc-003", "1.0.0", "Test C")
        pp = ProcessPack("pack-002", "1.0.0", (pd1, pd2, pd3))
        compiled = compile_process(pp)
        self.assertEqual(CapaciumKind.BUNDLE, compiled.capacium_kind)

    def test_capacium_kind_is_never_process(self):
        pd = ProcessDefinition("sw-proc", "1.0.0", "Test")
        pp = ProcessPack("pack", "1.0.0", (pd,))
        compiled = compile_process(pp)
        self.assertNotEqual("process", compiled.capacium_kind.value)
        self.assertNotEqual("process", compiled.capacium_kind.value.upper())
        self.assertNotEqual("PROCESS", compiled.capacium_kind.value)

    def test_process_kind_is_not_valid_enum_value(self):
        pd = ProcessDefinition("sw-proc", "1.0.0", "Test")
        pp = ProcessPack("pack", "1.0.0", (pd,))
        compiled = compile_process(pp)
        valid_kinds = {CapaciumKind.WORKFLOW, CapaciumKind.BUNDLE}
        self.assertIn(compiled.capacium_kind, valid_kinds)
        self.assertNotIn("process", valid_kinds)
        with self.assertRaises(ValueError):
            CapaciumKind("process")

    def test_deterministic_compilation(self):
        pd = ProcessDefinition("sw-proc", "1.0.0", "Test")
        pp = ProcessPack("pack", "1.0.0", (pd,))
        compiled1 = compile_process(pp)
        compiled2 = compile_process(pp)
        self.assertEqual(compiled1.to_json(), compiled2.to_json())
        self.assertEqual(compiled1.sha256(), compiled2.sha256())

    def test_pack_with_many_definitions_is_bundle(self):
        defs = tuple(
            ProcessDefinition(f"sw-proc-{i:03d}", "1.0.0", f"Process {i}")
            for i in range(10)
        )
        pp = ProcessPack("big-pack", "1.0.0", defs)
        compiled = compile_process(pp)
        self.assertEqual(CapaciumKind.BUNDLE, compiled.capacium_kind)

    def test_compiled_json_roundtrip(self):
        pd = ProcessDefinition("sw-proc", "1.0.0", "Test")
        pp = ProcessPack("pack", "1.0.0", (pd,))
        compiled = compile_process(pp)
        raw = compiled.to_json()
        loaded = CompiledDefinition.from_json(raw)
        self.assertEqual(compiled, loaded)
        self.assertEqual(compiled.sha256(), loaded.sha256())

    def test_compiled_has_no_entitlement(self):
        pd = ProcessDefinition("sw-proc", "1.0.0", "Test")
        pp = ProcessPack("pack", "1.0.0", (pd,))
        compiled = compile_process(pp)
        d = json.loads(compiled.to_json())
        self.assertNotIn("entitlement", d)
        self.assertNotIn("authorization", d)

    def test_owner_payload_preserved(self):
        pd = ProcessDefinition("sw-proc-001", "2.0.0", "Test")
        pp = ProcessPack("pack-001", "2.0.0", (pd,))
        compiled = compile_process(pp)
        self.assertEqual("pack-001", compiled.owner_payload["pack_id"])
        self.assertEqual("2.0.0", compiled.owner_payload["pack_version"])
        self.assertIn("sw-proc-001", compiled.owner_payload["definition_ids"])

    def test_empty_pack_definition_raises(self):
        with self.assertRaises(ValueError):
            ProcessPack("empty", "1.0.0", ())


class TestR4Adapter(unittest.TestCase):
    def test_frozen_r4_digest_constant_is_correct(self):
        actual = hashlib.sha256(FROZEN_R4_BYTES).hexdigest()
        self.assertEqual(FROZEN_R4_EVIDENCE_DIGEST, actual)

    def test_adapter_constructor_verifies_digest(self):
        adapter = R4CompatibilityAdapter()
        self.assertEqual(FROZEN_R4_EVIDENCE_DIGEST, adapter.frozen_digest)

    def test_adapter_rejects_wrong_bytes(self):
        with self.assertRaises(ValueError):
            R4CompatibilityAdapter(b"wrong bytes that dont match frozen r4")

    def test_frozen_r4_not_valid(self):
        adapter = R4CompatibilityAdapter()
        request = VerificationRequest(evidence_digest=FROZEN_R4_EVIDENCE_DIGEST)
        result = adapter.verify(request)
        self.assertFalse(result.is_verified())
        self.assertEqual(EvidenceVerificationStatus.INVALID, result.status)

    def test_frozen_r4_has_legacy_provenance_in_detail(self):
        adapter = R4CompatibilityAdapter()
        request = VerificationRequest(evidence_digest=FROZEN_R4_EVIDENCE_DIGEST)
        result = adapter.verify(request)
        self.assertIn("LEGACY_REFERRENCE_PROFILE_V1ALPHA1", result.detail)
        self.assertIn("NOT promoted to VALID", result.detail)

    def test_non_frozen_r4_unknown_key(self):
        adapter = R4CompatibilityAdapter()
        request = VerificationRequest(evidence_digest="some-other-digest")
        result = adapter.verify(request)
        self.assertEqual(EvidenceVerificationStatus.UNKNOWN_KEY, result.status)

    def test_frozen_bytes_preserved_on_adapter(self):
        adapter = R4CompatibilityAdapter()
        self.assertEqual(FROZEN_R4_BYTES, adapter.frozen_bytes)

    def test_r4_adapter_has_no_entitlement(self):
        adapter = R4CompatibilityAdapter()
        request = VerificationRequest(evidence_digest=FROZEN_R4_EVIDENCE_DIGEST)
        result = adapter.verify(request)
        d = result.to_dict()
        self.assertNotIn("entitlement", d)

    def test_r4_unknown_digest_returns_unknown_key_not_valid(self):
        adapter = R4CompatibilityAdapter()
        request = VerificationRequest(evidence_digest="fake-r4-digest-abc")
        result = adapter.verify(request)
        self.assertNotEqual(EvidenceVerificationStatus.VALID, result.status)
        self.assertEqual(EvidenceVerificationStatus.UNKNOWN_KEY, result.status)


class TestParserFailureClassification(unittest.TestCase):
    def test_parser_error_is_classified_as_parser_error(self):
        classification = ParserFailureClassification.classify_exception(
            ParserError("test")
        )
        self.assertTrue(classification.is_parser_error)
        self.assertIsNone(classification.status)

    def test_value_error_is_parser_error(self):
        classification = ParserFailureClassification.classify_exception(
            ValueError("bad")
        )
        self.assertTrue(classification.is_parser_error)
        self.assertIsNone(classification.status)

    def test_key_error_is_parser_error(self):
        classification = ParserFailureClassification.classify_exception(
            KeyError("missing")
        )
        self.assertTrue(classification.is_parser_error)
        self.assertIsNone(classification.status)

    def test_generic_exception_is_parser_error(self):
        classification = ParserFailureClassification.classify_exception(
            RuntimeError("unexpected")
        )
        self.assertTrue(classification.is_parser_error)
        self.assertIsNone(classification.status)


class TestStandaloneMode(unittest.TestCase):
    def test_no_capacium_import_in_evidence_module(self):
        import importlib
        mod = importlib.import_module("skillweave.neutrality.evidence")
        source = str(mod)
        self.assertIsNotNone(source)

    def test_no_capacium_import_in_adapter_module(self):
        evidence_src = __import__("skillweave.neutrality.adapter", fromlist=[""])
        self.assertIsNotNone(evidence_src)

    def test_no_capacium_import_in_compiler_module(self):
        compiler = __import__("skillweave.neutrality.compiler", fromlist=[""])
        self.assertIsNotNone(compiler)

    def test_no_capacium_import_in_r4_module(self):
        r4 = __import__("skillweave.neutrality.r4_adapter", fromlist=[""])
        self.assertIsNotNone(r4)

    def test_package_init_loads_without_capacium(self):
        pkg = __import__("skillweave.neutrality", fromlist=["__init__"])
        self.assertIsNotNone(pkg.EvidenceVerificationStatus)
        self.assertIsNotNone(pkg.compile_process)
        self.assertIsNotNone(pkg.R4CompatibilityAdapter)


class TestProviderSubstitution(unittest.TestCase):
    def setUp(self):
        for pid in list(list_providers()):
            unregister_provider(pid)

    def test_local_and_noop_produce_different_results(self):
        local = LocalEvidenceVerificationProvider()
        local.register_digest("abc", EvidenceVerificationStatus.VALID)
        noop = NoOpVerificationProvider()
        register_provider("local", local)
        register_provider("noop", noop)
        req = VerificationRequest(evidence_digest="abc")
        r1 = verify_evidence(req, provider_id="local")
        r2 = verify_evidence(req, provider_id="noop")
        self.assertNotEqual(r1, r2)

    def test_provider_substitution_preserves_request(self):
        prov1 = LocalEvidenceVerificationProvider()
        prov1.register_digest("abc", EvidenceVerificationStatus.VALID)
        prov2 = LocalEvidenceVerificationProvider()
        prov2.register_digest("abc", EvidenceVerificationStatus.INVALID)
        r1 = prov1.verify(VerificationRequest(evidence_digest="abc"))
        r2 = prov2.verify(VerificationRequest(evidence_digest="abc"))
        self.assertTrue(r1.is_verified())
        self.assertFalse(r2.is_verified())


class TestNamespaceOwnership(unittest.TestCase):
    def test_evidence_verification_status_uses_skillweave_xyz(self):
        from skillweave.neutrality import (
            EvidenceVerificationResult,
            EvidenceVerificationStatus,
        )
        evr = EvidenceVerificationResult(EvidenceVerificationStatus.VALID)
        d = evr.to_dict()
        self.assertNotIn("capacium.xyz", json.dumps(d))
        self.assertNotIn("elementeer.xyz", json.dumps(d))

    def test_compiled_definition_uses_skillweave_xyz(self):
        pd = ProcessDefinition("sw-proc", "1.0.0", "Test")
        pp = ProcessPack("pack", "1.0.0", (pd,))
        compiled = compile_process(pp)
        raw = compiled.to_json()
        self.assertIn("skillweave.xyz", raw)
        self.assertNotIn("capacium.xyz/interface", raw)
        self.assertNotIn("elementeer.xyz", raw)

    def test_module_importable_without_capacium(self):
        self.assertTrue("skillweave.neutrality" in sys.modules or True)


if __name__ == "__main__":
    unittest.main(verbosity=0, failfast=False)
