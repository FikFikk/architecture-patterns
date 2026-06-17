"""
Example: Circuit Breaker dengan FastAPI dan External Payment Service
"""

import requests
from fastapi import FastAPI, HTTPException
from circuit_breaker import CircuitBreaker, CircuitBreakerError

app = FastAPI()

# Setup circuit breaker untuk payment service
payment_breaker = CircuitBreaker(
    failure_threshold=5,
    success_threshold=2,
    timeout=60,
    expected_exception=requests.RequestException
)


@app.post("/api/checkout")
async def checkout(order_id: str, amount: float, user_id: str):
    """
    Checkout endpoint dengan circuit breaker protection
    """
    try:
        result = payment_breaker.call(
            process_payment,
            order_id=order_id,
            amount=amount,
            user_id=user_id
        )
        return {
            "status": "success",
            "transaction_id": result["transaction_id"],
            "message": "Payment processed successfully"
        }
    
    except CircuitBreakerError as e:
        # Circuit open: queue untuk retry nanti
        queue_payment_for_retry(order_id, amount, user_id)
        return {
            "status": "queued",
            "message": "Payment service temporarily unavailable. Your order will be processed shortly.",
            "order_id": order_id
        }
    
    except requests.RequestException as e:
        raise HTTPException(
            status_code=503,
            detail=f"Payment service error: {str(e)}"
        )


@app.get("/health/circuit-breaker")
async def circuit_breaker_health():
    """
    Health check endpoint untuk monitoring
    """
    metrics = payment_breaker.get_metrics()
    return {
        "service": "payment-gateway",
        "circuit_breaker": metrics,
        "healthy": metrics["state"] != "OPEN"
    }


def process_payment(order_id: str, amount: float, user_id: str) -> dict:
    """
    Actual payment processing logic
    """
    response = requests.post(
        "https://payment-gateway.example.com/api/charge",
        json={
            "order_id": order_id,
            "amount": amount,
            "user_id": user_id,
            "currency": "USD"
        },
        timeout=5,
        headers={"Authorization": "Bearer YOUR_API_KEY"}
    )
    response.raise_for_status()
    return response.json()


def queue_payment_for_retry(order_id: str, amount: float, user_id: str):
    """
    Queue payment untuk retry saat service kembali normal
    Implementasi: Redis queue, RabbitMQ, atau SQS
    """
    # Simplified - gunakan message queue di production
    print(f"Queued payment for retry: {order_id}, amount: {amount}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
