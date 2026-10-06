from locust import HttpUser, task, between

class KanyaRakshakUser(HttpUser):
    wait_time = between(1, 2)

    @task
    def trigger_sos(self):
        self.client.post(
            "/api/v1/voice-distress",
            data={
                "session_id": "locust_test_user",
                "latitude": "17.3850",
                "longitude": "78.4867"
            },
            files={
                "audio_file": (
                    "sos.wav",
                    b"test audio data",
                    "audio/wav"
                )
            }
        )