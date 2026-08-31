import pytest
from skillweave.routing.faigate_adapter import is_substitution, detect_substitution, AttributedResponse, translate_model_id, ROUTER_PROFILES

def test_model_substitution_visibility():
    # Assert that requesting at least two models results in two distinct resolved/answering models,
    # ensuring substitution is visible.
    
    # 1. requested model = sonnet, served_by = claude-3-5-sonnet -> mapped alias
    requested_1 = "sonnet"
    served_1 = "anthropic-sonnet"
    assert is_substitution(requested_1, served_1, provider="faigate") == False # because sonnet maps to anthropic-sonnet

    # 2. requested model = sonnet, served_by = gemini-pro -> substitution!
    requested_2 = "sonnet"
    served_2 = "gemini-pro"
    assert is_substitution(requested_2, served_2, provider="faigate") == True
    
    # 3. Two distinct requested models should yield distinct answering models when no substitution
    ans1 = AttributedResponse("hello", requested_model="sonnet", answering_model="anthropic-sonnet", served_by="anthropic-sonnet", provider="faigate")
    ans2 = AttributedResponse("hello", requested_model="gpt-4o", answering_model="openai-gpt4o", served_by="openai-gpt4o", provider="faigate")
    
    assert ans1.answering_model != ans2.answering_model
    assert ans1.is_substituted == False
    assert ans2.is_substituted == False

    # 4. If they both collapse to the same fallback model, substitution is visible
    ans3 = AttributedResponse("hello", requested_model="sonnet", answering_model="deepseek-v4-flash", served_by="deepseek-v4-flash", provider="faigate")
    ans4 = AttributedResponse("hello", requested_model="gpt-4o", answering_model="deepseek-v4-flash", served_by="deepseek-v4-flash", provider="faigate")
    
    assert ans3.answering_model == ans4.answering_model
    assert ans3.is_substituted == True
    assert ans4.is_substituted == True

def test_router_profiles_diversity():
    # The requirement is that requesting >= 2 models results in distinct models (deepseek-v4-pro and deepseek-v4-flash)
    # the default profile uses: ["deepseek-v4-pro", "deepseek-v4-flash"]
    models = ROUTER_PROFILES["default"]["models"]
    assert len(models) >= 2
    assert len(set(models)) == len(models)
    
    # Simulate resolving them correctly
    ans1 = AttributedResponse("hello", requested_model=models[0], answering_model=models[0], served_by=models[0], provider="faigate")
    ans2 = AttributedResponse("hello", requested_model=models[1], answering_model=models[1], served_by=models[1], provider="faigate")
    
    # They should be distinct and not substituted
    assert ans1.answering_model != ans2.answering_model
    assert not ans1.is_substituted
    assert not ans2.is_substituted


def test_comparison_run_documents_models_and_limits():
    # SW-PROFILE-EXPAND-001: ensure comparison runs document requested/resolved/answering models and usage limits
    import yaml
    import os
    
    # Load comparison profile
    profile_path = os.path.join(os.path.dirname(__file__), '../../config/profiles/comparison.yaml')
    if not os.path.exists(profile_path):
        pytest.skip("Comparison profile not found")
        
    with open(profile_path, 'r') as f:
        profile_data = yaml.safe_load(f)
        
    limits = profile_data.get('limits', {})
    assert 'timeout' in limits
    assert 'max_retries' in limits
    assert 'min_models_required' in limits
    assert limits['min_models_required'] >= 2
    
    # Simulate a comparison run
    requested_ops = profile_data['roles']['ops']['model']
    requested_rev = profile_data['roles']['reviewer']['model']
    
    # Documenting requested/resolved/answering models via AttributedResponse
    ops_ans = AttributedResponse("ops result", requested_model=requested_ops, answering_model="deepseek-v4-pro", served_by="deepseek-v4-pro", provider="faigate")
    rev_ans = AttributedResponse("review result", requested_model=requested_rev, answering_model="deepseek-v4-pro", served_by="deepseek-v4-pro", provider="faigate")
    
    # Asserting that these are tracked
    assert ops_ans.requested_model == requested_ops
    assert ops_ans.answering_model == "deepseek-v4-pro"
    assert rev_ans.requested_model == requested_rev
    assert rev_ans.answering_model == "deepseek-v4-pro"
