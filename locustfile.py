from locust import HttpUser, task, between

class SafetyAppUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def chat(self):
        self.client.post("/api/v1/chat", json={
            "session_id": "load_test_user",
            "message": "Is Hyderabad safe?"
        })