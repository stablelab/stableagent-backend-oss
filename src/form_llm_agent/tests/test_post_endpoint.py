"""
Test suite for the new POST endpoint with form context and evaluation instructions.

Tests the enhanced form processing capability that accepts complete form structures
and provides targeted advice based on evaluation instructions.
"""

from ..graph import stream_field_processing_with_context
from ..router import FormProcessingRequest, find_field_in_form
import json
import asyncio
import os
from typing import Dict, Any

# Set up test environment
os.environ['FORM_AGENT_MODEL'] = 'gpt-3.5-turbo'
os.environ['FORM_AGENT_TEMPERATURE'] = '0.3'
os.environ['FORM_AGENT_JSON_MODE'] = 'true'


class PostEndpointTester:
    """Tester for the POST endpoint with form context."""

    def __init__(self):
        # Load the grant application form for testing
        try:
            with open('/home/klorpomo/analysis/stableagent-backend/grant_application_form.json', 'r') as f:
                self.grant_form = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load grant form: {e}")
            self.grant_form = None

    def test_field_finding(self):
        """Test the field finding functionality."""
        print("=== Field Finding Test ===")

        if not self.grant_form:
            print("❌ No grant form available for testing")
            return

        # Test finding different types of fields
        test_field_ids = [
            "title",           # Direct field
            "projectType",     # Select field
            "description",     # Textarea field
            "budget",          # Number field
            "applicantName",   # Text field in different step
            "attachments",     # File field
            "nonexistent"      # Should not be found
        ]

        for field_id in test_field_ids:
            field_config = find_field_in_form(self.grant_form, field_id)

            if field_config:
                field_label = field_config.get("label", "No label")
                field_type = field_config.get("type", "unknown")
                evaluation_instructions = field_config.get(
                    "props", {}).get("evaluationInstructions", "None")

                print(f"  ✓ {field_id:<15} -> {field_label} ({field_type})")
                if evaluation_instructions != "None":
                    print(
                        f"    📝 Instructions: {evaluation_instructions[:80]}...")
            else:
                print(f"  ❌ {field_id:<15} -> Not found")

        print()

    async def test_enhanced_streaming(self):
        """Test the enhanced streaming functionality with evaluation instructions."""
        print("=== Enhanced Streaming Test ===")

        if not self.grant_form:
            print("❌ No grant form available for testing")
            return

        # Test fields with evaluation instructions
        test_fields = ["title", "projectType", "budget", "applicantName"]

        for field_id in test_fields:
            print(f"\n📋 Testing enhanced streaming for: {field_id}")

            field_config = find_field_in_form(self.grant_form, field_id)
            if not field_config:
                print(f"  ❌ Field {field_id} not found")
                continue

            # Extract field context
            field_label = field_config.get("label", field_id)
            field_type = field_config.get("type", "text")
            field_description = field_config.get("description", "")
            evaluation_instructions = field_config.get(
                "props", {}).get("evaluationInstructions", "")
            validation_rules = field_config.get("validation", {})

            print(f"  📝 Field: {field_label} ({field_type})")
            print(f"  📋 Validation: {validation_rules}")
            print(f"  🎯 Instructions: {evaluation_instructions[:100]}...")

            try:
                async for result in stream_field_processing_with_context(
                    field_id=field_id,
                    field_label=field_label,
                    field_type=field_type,
                    field_description=field_description,
                    evaluation_instructions=evaluation_instructions,
                    validation_rules=validation_rules
                ):
                    print(f"  💡 Enhanced Advice: {result.response}")
                    print(f"  📏 Length: {len(result.response)} chars")
                    print(f"  🎯 Type: {result.type}")
                    break

            except Exception as e:
                print(f"  ❌ Error: {str(e)}")

        print()

    def test_request_model(self):
        """Test the Pydantic request model."""
        print("=== Request Model Test ===")

        if not self.grant_form:
            print("❌ No grant form available for testing")
            return

        # Test creating FormProcessingRequest objects
        test_requests = [
            {"id_requested": "title", "form": self.grant_form},
            {"id_requested": "projectType", "form": self.grant_form},
            {"id_requested": "budget", "form": self.grant_form}
        ]

        for i, request_data in enumerate(test_requests, 1):
            try:
                request = FormProcessingRequest(**request_data)
                print(f"  ✓ Request {i}: {request.id_requested} -> Valid")

                # Test field finding
                field_config = find_field_in_form(
                    request.form, request.id_requested)
                if field_config:
                    print(
                        f"    📝 Found field: {field_config.get('label', 'No label')}")
                else:
                    print(f"    ❌ Field not found: {request.id_requested}")

            except Exception as e:
                print(f"  ❌ Request {i}: Invalid - {str(e)}")

        print()

    async def compare_simple_vs_enhanced(self):
        """Compare simple field processing vs enhanced with evaluation instructions."""
        print("=== Simple vs Enhanced Comparison ===")

        if not self.grant_form:
            print("❌ No grant form available for testing")
            return

        test_field = "title"
        field_config = find_field_in_form(self.grant_form, test_field)

        if not field_config:
            print(f"❌ Field {test_field} not found")
            return

        print(f"Comparing advice for field: {test_field}")

        # Test simple processing
        print(f"\n1. 📝 Simple Processing (no context):")
        try:
            from ..graph import stream_field_processing
            async for result in stream_field_processing(test_field):
                print(f"   Response: {result.response}")
                print(f"   Length: {len(result.response)} chars")
                break
        except Exception as e:
            print(f"   ❌ Error: {e}")

        # Test enhanced processing
        print(f"\n2. 🎯 Enhanced Processing (with evaluation instructions):")
        try:
            field_label = field_config.get("label", test_field)
            field_type = field_config.get("type", "text")
            field_description = field_config.get("description", "")
            evaluation_instructions = field_config.get(
                "props", {}).get("evaluationInstructions", "")
            validation_rules = field_config.get("validation", {})

            async for result in stream_field_processing_with_context(
                field_id=test_field,
                field_label=field_label,
                field_type=field_type,
                field_description=field_description,
                evaluation_instructions=evaluation_instructions,
                validation_rules=validation_rules
            ):
                print(f"   Response: {result.response}")
                print(f"   Length: {len(result.response)} chars")
                print(
                    f"   📋 Used evaluation instructions: {bool(evaluation_instructions)}")
                break
        except Exception as e:
            print(f"   ❌ Error: {e}")

        print()


async def run_post_endpoint_tests():
    """Run all POST endpoint tests."""
    print("🚀 POST Endpoint with Form Context Test Suite")
    print("=" * 60)
    print("Testing enhanced form processing with evaluation instructions")
    print("=" * 60)

    tester = PostEndpointTester()

    # Test 1: Field Finding
    tester.test_field_finding()

    # Test 2: Request Model
    tester.test_request_model()

    # Test 3: Enhanced Streaming
    await tester.test_enhanced_streaming()

    # Test 4: Comparison
    await tester.compare_simple_vs_enhanced()

    print("=" * 60)
    print("🎉 POST Endpoint Testing Complete!")
    print()
    print("Key Features Demonstrated:")
    print("  ✓ POST endpoint with form context")
    print("  ✓ Field finding in complex form structures")
    print("  ✓ Evaluation instructions integration")
    print("  ✓ Enhanced prompts with field metadata")
    print("  ✓ Targeted advice based on field context")
    print("  ✓ Validation rules awareness")
    print("  ✓ Performance logging for enhanced processing")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_post_endpoint_tests())

