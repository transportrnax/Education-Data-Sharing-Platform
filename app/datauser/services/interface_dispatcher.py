import requests

def dispatch_service_request(config: dict, input_data) -> dict:
    """
    Dynamically dispatches a service request based on the saved config.

    :param config: dict with keys: base_url, path, method, input, output
    :param input_data: dict or list[dict] from user input (UI form)
    :return: dict or list of dicts: response(s) from target service
    """
    try:
        base_url = config["base_url"].rstrip('/')
        path = config["path"].lstrip('/')
        method = config["method"].lower()
        expected_inputs = config["input"]

        url = f"{base_url}/{path}"

        def build_payload(data: dict) -> dict:
            return {k: data.get(k, "") for k in expected_inputs.keys()}

        if isinstance(input_data, list):
            # 👥 Batch input: dispatch one by one
            responses = []
            for item in input_data:
                payload = build_payload(item)
                print(f"[Dispatcher] POST {url} with payload: {payload}")
                try:
                    res = requests.post(url, json=payload, timeout=5) if method == "post" else requests.get(url, params=payload, timeout=5)
                    try:
                        responses.append(res.json())
                    except:
                        responses.append({"raw": res.text, "status_code": res.status_code})
                except Exception as ex:
                    responses.append({"error": f"DISPATCH_FAILED: {str(ex)}"})
            return responses

        # 👤 Single input
        payload = build_payload(input_data)
        print(f"[Dispatcher] {method.upper()} {url} with payload: {payload}")

        if method == "post":
            res = requests.post(url, json=payload, timeout=5)
        elif method == "get":
            res = requests.get(url, params=payload, timeout=5)
        else:
            return {"error": f"Unsupported HTTP method: {method}"}

        try:
            return res.json()
        except Exception:
            return {"raw": res.text, "status_code": res.status_code}

    except Exception as e:
        return {"error": f"DISPATCH_FAILED: {str(e)}"}
