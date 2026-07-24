# BRIO Waitlist API

Context-aware, fraud-resistant waitlist infrastructure for modern SaaS. 

Stop using basic "+1 point" logic. BRIO uses LLMs to generate dynamic referral copy, graph-based behavioral analysis to prevent spam, and weighted algorithms to prioritize high-value leads.

## Advanced Features

- **Semantic Referral Generation:** Automatically writes personalized referral messages based on the user's signup source and industry.
- **Behavioral Fraud Graphing:** Maps referrals as a network graph. Instantly flags coordinated spam rings (e.g., users referring themselves from the same IP cluster in seconds).
- **Weighted Queue Positioning:** Not all signups are equal. A `.com` enterprise email moves a user up the queue faster than a generic `.gmail` address.
- **Token Architecture:** Built on BRIO's standard token-metering system. Perfect for testing how BRIO's enterprise APIs handle billing and limits.

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/signup` | Register user, trigger fraud check, generate LLM copy |
| `GET` | `/v1/position` | Get current queue position & status |
| `GET` | `/v1/referral-text` | Fetch the AI-generated sharing text |

## Quick Start

1. Add your `OPENAI_API_KEY` to your environment variables.
2. Run the server: `uvicorn main:app --host 0.0.0.0 --port 8000`
3. Send a test signup:
```bash
curl -X POST https://your-url.com/v1/signup \
-H "Authorization: Bearer brio_test_key" \
-H "Content-Type: application/json" \
-d '{"email": "test@company.com", "source": "twitter", "industry": "marketing"}'
```

## Built by BRIO
BRIO builds highly advanced API infrastructure.
