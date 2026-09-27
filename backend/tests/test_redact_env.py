from app.features.investigation.tools import redact_env


def test_hides_secret_values_but_keeps_names():
    env = {
        "PG_HOST": "postgres",
        "PG_PORT": None,
        "PG_PASSWORD": "sentinel",
        "API_KEY": "abc",
        "auth_token": "xyz",
        "CLIENT_SECRET": "s3",
    }
    assert redact_env(env) == {
        "PG_HOST": "postgres",
        "PG_PORT": None,
        "PG_PASSWORD": "[hidden]",
        "API_KEY": "[hidden]",
        "auth_token": "[hidden]",
        "CLIENT_SECRET": "[hidden]",
    }


def test_unset_secret_stays_unset():
    assert redact_env({"PG_PASSWORD": None}) == {"PG_PASSWORD": None}
