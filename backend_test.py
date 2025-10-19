#!/usr/bin/env python3
"""
Backend API Testing Script
Tests basic health endpoints and API connectivity
"""

import requests
import json
import sys
from datetime import datetime

# Base URL from frontend .env
BASE_URL = "https://analise-detalhada.preview.emergentagent.com"

def test_endpoint(url, expected_status=200, description=""):
    """Test a single endpoint and return results"""
    print(f"\n🔍 Testing: {description}")
    print(f"URL: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        print(f"Status: {response.status_code}")
        
        # Try to parse JSON response
        try:
            json_data = response.json()
            print(f"Response: {json.dumps(json_data, indent=2)}")
        except:
            print(f"Response (text): {response.text[:200]}...")
        
        # Check if status matches expected
        if response.status_code == expected_status:
            print("✅ PASS")
            return True, response.status_code, json_data if 'json_data' in locals() else response.text
        else:
            print(f"❌ FAIL - Expected {expected_status}, got {response.status_code}")
            return False, response.status_code, json_data if 'json_data' in locals() else response.text
            
    except requests.exceptions.RequestException as e:
        print(f"❌ FAIL - Request error: {e}")
        return False, None, str(e)

def main():
    """Run all backend health tests"""
    print("=" * 60)
    print("🚀 BACKEND HEALTH CHECK TESTS")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"Test Time: {datetime.now().isoformat()}")
    
    results = []
    
    # Test 1: GET /health (without prefix)
    success, status, response = test_endpoint(
        f"{BASE_URL}/health",
        expected_status=200,
        description="Health check without /api prefix"
    )
    results.append({
        "endpoint": "/health",
        "success": success,
        "status": status,
        "response": response
    })
    
    # Test 2: GET /api/health
    success, status, response = test_endpoint(
        f"{BASE_URL}/api/health",
        expected_status=200,
        description="Health check with /api prefix"
    )
    results.append({
        "endpoint": "/api/health",
        "success": success,
        "status": status,
        "response": response
    })
    
    # Test 3: GET /api/health/ready (can be 200 or 503)
    success, status, response = test_endpoint(
        f"{BASE_URL}/api/health/ready",
        expected_status=200,  # We'll check for both 200 and 503 below
        description="Readiness check - should return JSON with details.env and details.mongo"
    )
    
    # For readiness check, both 200 and 503 are acceptable
    if status in [200, 503]:
        success = True
        print("✅ Status 200 or 503 is acceptable for readiness check")
        
        # Validate JSON structure
        if isinstance(response, dict):
            if 'details' in response and 'env' in response['details'] and 'mongo' in response['details']:
                print("✅ JSON structure is correct (has details.env and details.mongo)")
            else:
                print("❌ JSON structure missing required fields (details.env, details.mongo)")
                success = False
    
    results.append({
        "endpoint": "/api/health/ready",
        "success": success,
        "status": status,
        "response": response
    })
    
    # Test 4: GET /api/ (root with prefix)
    success, status, response = test_endpoint(
        f"{BASE_URL}/api/",
        expected_status=200,
        description="API root endpoint - should return message"
    )
    
    # Validate message field exists
    if success and isinstance(response, dict) and 'message' in response:
        print("✅ Response contains 'message' field")
    elif success:
        print("❌ Response missing 'message' field")
        success = False
    
    results.append({
        "endpoint": "/api/",
        "success": success,
        "status": status,
        "response": response
    })
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r['success'])
    
    for result in results:
        status_icon = "✅" if result['success'] else "❌"
        print(f"{status_icon} {result['endpoint']} - Status: {result['status']}")
    
    print(f"\nResults: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("🎉 All backend health checks PASSED!")
        return 0
    else:
        print("⚠️  Some backend health checks FAILED!")
        return 1

if __name__ == "__main__":
    sys.exit(main())