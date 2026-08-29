"""
Suite de tests unitaires pour l'agent EWER.
Exécute tous les tests avec des mocks complets des APIs externes (Gemini, Firestore, Cloud Storage, requests, Flask, Folium).
"""
import base64
import datetime
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock des dépendances externes dans sys.modules si non installées localement
def _setup_mock_modules():
    mocks = [
        "flask",
        "requests",
        "folium",
        "google",
        "google.genai",
        "google.genai.types",
        "google.cloud",
        "google.cloud.firestore",
        "google.cloud.storage",
        "google.adk",
        "google.adk.agents",
        "google.adk.tools",
    ]
    for mod in mocks:
        if mod not in sys.modules:
            mock_mod = MagicMock()
            if mod == "flask":
                mock_flask_app = MagicMock()
                mock_flask_app.route.return_value = lambda f: f
                mock_mod.Flask.return_value = mock_flask_app
                mock_mod.jsonify = lambda x: x
            sys.modules[mod] = mock_mod

_setup_mock_modules()


# Ajouter agent au PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agent")))

import indicators
import geo_lookup
import notifier
import integration_adapter
import gemini_analysis
import memory_store
import monthly_report
import ewer_adk_agent
import main


class TestIndicators(unittest.TestCase):
    def test_indicator_categories(self):
        self.assertIn("security_incidents", indicators.INDICATOR_CATEGORIES)
        self.assertIn("intercommunity_relations", indicators.INDICATOR_CATEGORIES)
        self.assertEqual(len(indicators.INDICATOR_CATEGORIES), 7)

    def test_risk_levels(self):
        self.assertIn("low", indicators.RISK_LEVELS)
        self.assertIn("moderate", indicators.RISK_LEVELS)
        self.assertIn("high", indicators.RISK_LEVELS)
        self.assertIn("critical", indicators.RISK_LEVELS)


class TestGeoLookup(unittest.TestCase):
    def test_known_communes(self):
        coords = geo_lookup.get_coords("Banikoara")
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords[0], 11.3000, places=3)

    def test_unknown_or_none(self):
        self.assertIsNone(geo_lookup.get_coords(None))
        self.assertIsNone(geo_lookup.get_coords(""))
        self.assertIsNone(geo_lookup.get_coords("Tokyo"))

    def test_case_insensitive_and_prefixes(self):
        self.assertIsNotNone(geo_lookup.get_coords("banikoara"))
        self.assertIsNotNone(geo_lookup.get_coords("Commune de Kandi"))
        self.assertIsNotNone(geo_lookup.get_coords("commune de malanville"))
        self.assertIsNotNone(geo_lookup.get_coords("Kerou"))


class TestNotifier(unittest.TestCase):
    def test_format_alert_message_standard(self):
        analysis = {
            "zone": "Banikoara",
            "risk_level": "high",
            "composite_score": 7.2,
            "summary_fr": "Tensions signalées",
            "recommended_action": "Déployer une médiation",
            "indicators_detected": [
                {"category": "security_incidents", "intensity": 7, "evidence": "Affrontements"}
            ]
        }
        msg = notifier.format_alert_message(analysis)
        self.assertIn("Banikoara", msg)
        self.assertIn("HIGH", msg)
        self.assertIn("7.2/10", msg)
        self.assertIn("Affrontements", msg)

    def test_format_alert_message_with_escalation(self):
        analysis = {"zone": "Banikoara", "risk_level": "moderate", "composite_score": 5.0}
        escalation = {
            "trigger_count": 3,
            "window_days": 14,
            "escalated_to": "high"
        }
        msg = notifier.format_alert_message(analysis, escalation=escalation)
        self.assertIn("ESCALADE AUTOMATIQUE", msg)
        self.assertIn("HIGH", msg)

    def test_format_alert_message_safe_none(self):
        analysis = {"risk_level": None, "indicators_detected": [{}]}
        msg = notifier.format_alert_message(analysis)
        self.assertIn("INCONNU", msg)

    @patch("notifier.requests.post")
    def test_send_notification_demo_mode(self, mock_post):
        with patch.dict(os.environ, {}, clear=True):
            res = notifier.send_notification({"zone": "Kandi"})
            self.assertTrue(res)
            mock_post.assert_not_called()

    @patch("notifier.requests.post")
    def test_send_notification_webhook(self, mock_post):
        mock_post.return_value.raise_for_status = MagicMock()
        with patch.dict(os.environ, {"ALERT_WEBHOOK_URL": "https://example.com/webhook"}):
            res = notifier.send_notification({"zone": "Kandi"})
            self.assertTrue(res)
            mock_post.assert_called_once()


class TestIntegrationAdapter(unittest.TestCase):
    def test_to_standard_schema(self):
        analysis = {
            "zone": "Malanville",
            "risk_level": "critical",
            "composite_score": 9.0,
            "summary_fr": "Incident grave",
            "recommended_action": "Intervention urgente",
            "indicators_detected": [{"category": "security_incidents"}],
            "source_id": "src-123"
        }
        schema = integration_adapter.to_standard_schema(analysis)
        self.assertEqual(schema["schema_version"], "ewer-agent-1.0")
        self.assertEqual(schema["location"]["name"], "Malanville")
        self.assertEqual(schema["severity"], "critical")
        self.assertIn("security_incidents", schema["indicator_categories"])

    @patch("integration_adapter.requests.post")
    def test_push_to_external_system_no_endpoint(self, mock_post):
        with patch.dict(os.environ, {}, clear=True):
            res = integration_adapter.push_to_external_system({"zone": "Kandi"})
            self.assertFalse(res)
            mock_post.assert_not_called()

    @patch("integration_adapter.requests.post")
    def test_push_to_external_system_with_endpoint(self, mock_post):
        mock_post.return_value.raise_for_status = MagicMock()
        with patch.dict(os.environ, {"EXTERNAL_EWS_ENDPOINT": "https://example.com/api", "EXTERNAL_EWS_API_KEY": "secret"}):
            res = integration_adapter.push_to_external_system({"zone": "Kandi"})
            self.assertTrue(res)
            mock_post.assert_called_once()


class TestGeminiAnalysis(unittest.TestCase):
    @patch("gemini_analysis.genai.Client")
    def test_analyze_report_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "zone": "Banikoara",
            "summary_fr": "Tensions agricoles",
            "indicators_detected": [{"category": "intercommunity_relations", "intensity": 6, "evidence": "Conflit foncier"}],
            "composite_score": 5.8,
            "risk_level": "high",
            "recommended_action": "Médiation"
        })
        mock_client.models.generate_content.return_value = mock_response

        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_key"}):
            result = gemini_analysis.analyze_report("Rapport de test", source_id="test-1")
            self.assertEqual(result["zone"], "Banikoara")
            self.assertEqual(result["risk_level"], "high")
            self.assertEqual(result["source_id"], "test-1")

    @patch("gemini_analysis.genai.Client")
    def test_analyze_report_with_markdown_fences(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = "```json\n" + json.dumps({
            "zone": "Kandi",
            "summary_fr": "Situation calme",
            "indicators_detected": [],
            "composite_score": 1.0,
            "risk_level": "low",
            "recommended_action": "Surveillance"
        }) + "\n```"
        mock_client.models.generate_content.return_value = mock_response

        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_key"}):
            result = gemini_analysis.analyze_report("Rapport calme")
            self.assertEqual(result["zone"], "Kandi")
            self.assertEqual(result["risk_level"], "low")


class TestMemoryStore(unittest.TestCase):
    def test_check_escalation_triggers(self):
        mock_db = MagicMock()
        now = datetime.datetime.now(datetime.timezone.utc)
        
        doc1 = MagicMock()
        doc1.to_dict.return_value = {"zone": "Banikoara", "risk_level": "moderate", "received_at": now - datetime.timedelta(days=2)}
        doc2 = MagicMock()
        doc2.to_dict.return_value = {"zone": "Banikoara", "risk_level": "moderate", "received_at": now - datetime.timedelta(days=5)}
        doc3 = MagicMock()
        doc3.to_dict.return_value = {"zone": "Banikoara", "risk_level": "moderate", "received_at": now - datetime.timedelta(days=8)}

        mock_query = MagicMock()
        mock_query.stream.return_value = [doc1, doc2, doc3]
        mock_db.collection.return_value.where.return_value = mock_query

        escalation = memory_store.check_escalation(mock_db, "Banikoara")
        self.assertIsNotNone(escalation)
        self.assertEqual(escalation["zone"], "Banikoara")
        self.assertEqual(escalation["escalated_to"], "high")
        self.assertEqual(escalation["trigger_count"], 3)

    def test_check_escalation_no_trigger(self):
        mock_db = MagicMock()
        now = datetime.datetime.now(datetime.timezone.utc)
        doc1 = MagicMock()
        doc1.to_dict.return_value = {"zone": "Banikoara", "risk_level": "moderate", "received_at": now - datetime.timedelta(days=2)}

        mock_query = MagicMock()
        mock_query.stream.return_value = [doc1]
        mock_db.collection.return_value.where.return_value = mock_query

        escalation = memory_store.check_escalation(mock_db, "Banikoara")
        self.assertIsNone(escalation)


class TestEwerAdkAgent(unittest.TestCase):
    @patch("gemini_analysis.analyze_report")
    @patch("memory_store.get_client")
    @patch("memory_store.store_report_analysis")
    @patch("memory_store.check_escalation")
    @patch("memory_store.store_alert")
    @patch("notifier.send_notification")
    @patch("integration_adapter.push_to_external_system")
    def test_process_and_act_critical_alerts(
        self, mock_push, mock_notify, mock_store_alert, mock_check_esc, mock_store_rep, mock_get_client, mock_analyze
    ):
        mock_analyze.return_value = {
            "zone": "Malanville",
            "risk_level": "critical",
            "composite_score": 9.5,
            "summary_fr": "Attaque armée",
            "indicators_detected": [{"category": "security_incidents", "intensity": 9, "evidence": "Tirs"}]
        }
        mock_check_esc.return_value = None
        mock_store_alert.return_value = "alert-456"
        mock_notify.return_value = True
        mock_push.return_value = True

        result = ewer_adk_agent.process_and_act("Rapport critique", source_id="test-crit")
        self.assertTrue(result["alert_triggered"])
        self.assertEqual(result["alert_id"], "alert-456")
        mock_store_alert.assert_called_once()
        mock_notify.assert_called_once()


class TestMonthlyReport(unittest.TestCase):
    @patch("memory_store.get_client")
    @patch("monthly_report.genai.Client")
    @patch("monthly_report.storage.Client")
    @patch("monthly_report.folium.Map")
    def test_generate_monthly_report(self, mock_folium_map, mock_storage_client, mock_genai_client, mock_get_client):
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db

        # Rapports Firestore
        doc1 = MagicMock()
        doc1.to_dict.return_value = {
            "zone": "Banikoara",
            "risk_level": "moderate",
            "composite_score": 5.0,
            "indicators_detected": [{"category": "intercommunity_relations"}],
            "summary_fr": "Tensions locales"
        }
        mock_db.collection.return_value.where.return_value.where.return_value.stream.return_value = [doc1]

        # Gemini
        mock_model = MagicMock()
        mock_genai_client.return_value.models.generate_content.return_value.text = json.dumps({
            "total_reports": 1,
            "zones_a_surveiller": ["Banikoara"],
            "categories_dominantes": ["intercommunity_relations"],
            "narrative_fr": "Mois marqué par des tensions à Banikoara."
        })

        # Storage
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client.return_value.bucket.return_value = mock_bucket

        with patch.dict(os.environ, {"GEMINI_API_KEY": "key", "EWER_REPORTS_BUCKET": "my-bucket"}):
            rep = monthly_report.generate_monthly_report(year=2026, month=8)
            self.assertEqual(rep["year"], 2026)
            self.assertEqual(rep["month"], 8)
            self.assertEqual(rep["total_reports"], 1)
            self.assertIn("Banikoara", rep["zones_a_surveiller"])
            self.assertTrue(rep["map_url"].startswith("https://storage.googleapis.com/my-bucket/"))


class TestMainEndpoints(unittest.TestCase):
    @patch("main.process_and_act")
    @patch("main.request")
    @patch("main.jsonify", side_effect=lambda x: x)
    def test_ingest_endpoint(self, mock_jsonify, mock_request, mock_process):
        mock_request.get_json.return_value = {"report_text": "Marché calme", "source_id": "test-1"}
        mock_process.return_value = {"alert_triggered": False, "analysis": {"risk_level": "low"}}
        res, status = main.ingest()
        self.assertEqual(status, 200)
        self.assertEqual(res["alert_triggered"], False)

    @patch("main.process_and_act")
    @patch("main.request")
    @patch("main.jsonify", side_effect=lambda x: x)
    def test_pubsub_push_json(self, mock_jsonify, mock_request, mock_process):
        mock_process.return_value = {"alert_triggered": True}
        raw_msg = json.dumps({"report_text": "Tension élevée", "source_id": "ps-1"})
        b64_data = base64.b64encode(raw_msg.encode("utf-8")).decode("utf-8")
        mock_request.get_json.return_value = {"message": {"data": b64_data, "messageId": "msg-123"}}

        res, status = main.pubsub_push()
        self.assertEqual(status, 200)
        self.assertEqual(res["status"], "processed")
        self.assertEqual(res["alert_triggered"], True)
        mock_process.assert_called_once_with("Tension élevée", source_id="ps-1")

    @patch("main.process_and_act")
    @patch("main.request")
    @patch("main.jsonify", side_effect=lambda x: x)
    def test_pubsub_push_plain_text(self, mock_jsonify, mock_request, mock_process):
        mock_process.return_value = {"alert_triggered": False}
        raw_msg = "Texte brut directement envoyé"
        b64_data = base64.b64encode(raw_msg.encode("utf-8")).decode("utf-8")
        mock_request.get_json.return_value = {"message": {"data": b64_data, "messageId": "msg-456"}}

        res, status = main.pubsub_push()
        self.assertEqual(status, 200)
        self.assertEqual(res["status"], "processed")
        mock_process.assert_called_once_with("Texte brut directement envoyé", source_id="msg-456")

    @patch("main.generate_monthly_report")
    @patch("main.request")
    @patch("main.jsonify", side_effect=lambda x: x)
    def test_monthly_report_trigger(self, mock_jsonify, mock_request, mock_gen_report):
        mock_gen_report.return_value = {"year": 2026, "month": 8, "total_reports": 5}
        mock_request.get_json.return_value = {"year": "2026", "month": "8"}

        res, status = main.monthly_report_trigger()
        self.assertEqual(status, 200)
        mock_gen_report.assert_called_once_with(year=2026, month=8)


if __name__ == "__main__":
    unittest.main()


