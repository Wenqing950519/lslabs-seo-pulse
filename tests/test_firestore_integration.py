"""Opt-in Firestore smoke test: isolated random namespace, cleaned in finally.

Set SEO_PULSE_TEST_FIRESTORE_PROJECT and use ADC or a short-lived
SEO_PULSE_TEST_ACCESS_TOKEN. No Google Analytics/Search Console calls are made.
"""
from concurrent.futures import ThreadPoolExecutor
import os
import secrets
import time
from uuid import uuid4

import pytest

from seo_pulse_mcp.admission import COLLECTION, FirestoreBackend, LimitExceeded, SharedAdmissionStore


@pytest.mark.skipif(not os.environ.get("SEO_PULSE_TEST_FIRESTORE_PROJECT"), reason="live Firestore is opt-in")
def test_live_atomic_budget_and_code_claim_across_independent_clients():
    from google.cloud import firestore
    from google.oauth2.credentials import Credentials

    token = os.environ.get("SEO_PULSE_TEST_ACCESS_TOKEN")
    options = {"credentials": Credentials(token)} if token else {}
    clients = [firestore.Client(project=os.environ["SEO_PULSE_TEST_FIRESTORE_PROJECT"], **options) for _ in range(2)]
    namespace, key = "audit-" + uuid4().hex, secrets.token_urlsafe(48)
    stores = [SharedAdmissionStore(FirestoreBackend("unused", client=client), namespace=namespace,
                                   hmac_key=key) for client in clients]
    documents = set()
    try:
        for store in stores:
            store.check_available()
        documents.add(stores[0]._id("global"))
        for subject in ("one", "two", "three", "four"):
            documents.add(stores[0]._id("user", subject))

        def reserve(index):
            try:
                return stores[index % 2].admit(("one", "two", "three", "four")[index],
                                               per_minute=2, per_day=2, daily_total=2)
            except LimitExceeded:
                return None

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(reserve, range(4)))
        assert sorted(value for value in results if value is not None) == [1, 2]
        code, expires = secrets.token_urlsafe(48), time.time() + 120
        documents.add(stores[0]._id("code", code))
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(lambda store: store.claim_code(code, expires), stores))
        assert claims.count(True) == 1
        restarted = SharedAdmissionStore(FirestoreBackend("unused", client=clients[1]),
                                         namespace=namespace, hmac_key=key)
        assert restarted.claim_code(code, expires) is False
    finally:
        # Only this test's exact document IDs; never scan/delete production records.
        for document in documents:
            clients[0].collection(COLLECTION).document(document).delete(timeout=5)
        for client in clients:
            client.close()
