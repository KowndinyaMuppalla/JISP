#!/usr/bin/env python
"""Live GeoAI integration tests against running API."""

import requests
import json
from typing import Dict, Any

BASE_URL = "http://localhost:8000"

def test_asset_risk():
    """Test asset_risk template."""
    print("\n[TEST 1] Asset Risk Explanation")
    print("-" * 60)
    
    payload = {
        "subject": "ASSET-PUMP-001",
        "template": "asset_risk",
        "context": {
            "finding_type": "flood_proximity",
            "severity_raw": 0.75,
            "metrics": {"proximity_km": 2.5},
            "signals": ["Active flood zone detected", "Water level rising"]
        }
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/explain", json=payload, timeout=30)
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            result = resp.json()
            print(f"Subject: {result['subject']}")
            print(f"Template: {result['template']}")
            print(f"Model: {result['model']}")
            print(f"Explanation (first 150 chars):\n{result['explanation'][:150]}...")
            print("✅ Test 1 PASSED")
            return True
        else:
            print(f"❌ Unexpected status: {resp.status_code}")
            print(f"Response: {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Test 1 FAILED: {e}")
        return False


def test_flood_change():
    """Test flood_explanation template."""
    print("\n[TEST 2] Flood Change Explanation")
    print("-" * 60)
    
    payload = {
        "subject": "FLOOD-ZONE-ABC",
        "template": "flood_explanation",
        "context": {
            "finding_type": "flood_change",
            "severity_raw": 0.82,
            "metrics": {
                "extent_change_percent": 35,
                "depth_increase_m": 0.8
            },
            "signals": ["Extent increased by 35%", "Depth increased by 0.8m"]
        }
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/explain", json=payload, timeout=30)
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            result = resp.json()
            print(f"Subject: {result['subject']}")
            print(f"Template: {result['template']}")
            print(f"Explanation (first 150 chars):\n{result['explanation'][:150]}...")
            print("✅ Test 2 PASSED")
            return True
        else:
            print(f"❌ Unexpected status: {resp.status_code}")
            print(f"Response: {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Test 2 FAILED: {e}")
        return False


def test_anomaly():
    """Test anomaly_summary template."""
    print("\n[TEST 3] Anomaly Explanation")
    print("-" * 60)
    
    payload = {
        "subject": "SENSOR-TEMP-001",
        "template": "anomaly_summary",
        "context": {
            "finding_type": "temperature_spike",
            "severity_raw": 0.65,
            "metrics": {
                "spike_degrees_c": 8.5,
                "spike_duration_hours": 6
            },
            "signals": ["Temperature spike detected"]
        }
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/explain", json=payload, timeout=30)
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            result = resp.json()
            print(f"Subject: {result['subject']}")
            print(f"Template: {result['template']}")
            print(f"Explanation (first 150 chars):\n{result['explanation'][:150]}...")
            print("✅ Test 3 PASSED")
            return True
        else:
            print(f"❌ Unexpected status: {resp.status_code}")
            print(f"Response: {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Test 3 FAILED: {e}")
        return False


def test_health():
    """Test health check."""
    print("\n[HEALTH] API Health Check")
    print("-" * 60)
    
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            result = resp.json()
            print(f"Health Status: {result['status']}")
            print(f"Service: {result['service']}")
            print(f"Version: {result['version']}")
            print("✅ Health check PASSED")
            return True
        else:
            print(f"❌ Health check FAILED: {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health check FAILED: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("JISP GEOAI INTEGRATION - LIVE API TESTS")
    print("=" * 60)
    
    results = {
        "health": test_health(),
        "asset_risk": test_asset_risk(),
        "flood_change": test_flood_change(),
        "anomaly": test_anomaly(),
    }
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:20} {status}")
    
    total_passed = sum(1 for v in results.values() if v)
    total_tests = len(results)
    
    print(f"\nTotal: {total_passed}/{total_tests} tests passed")
    
    if total_passed == total_tests:
        print("\n🎉 ALL TESTS PASSED - GEOAI INTEGRATION VERIFIED!")
    else:
        print(f"\n⚠️  {total_tests - total_passed} test(s) failed")
