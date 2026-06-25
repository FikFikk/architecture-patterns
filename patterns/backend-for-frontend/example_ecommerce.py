"""
Example: Real-world BFF implementation for e-commerce
Demonstrates kompleksitas BFF pattern dalam production scenario
"""

from fastapi import FastAPI, HTTPException, Header
from typing import Optional, List, Dict, Any
import asyncio
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

app = FastAPI(title="E-commerce BFF Example")


# Mock data untuk demonstration
MOCK_USERS = {
    "user-123": {
        "id": "user-123",
        "name": "John Doe",
        "email": "john@example.com",
        "membership": "premium",
        "cart_items": 3
    }
}

MOCK_PRODUCTS = {
    "prod-1": {
        "id": "prod-1",
        "name": "Laptop Pro",
        "price": 1299.99,
        "stock": 15,
        "images": ["laptop-1.jpg", "laptop-2.jpg"]
    },
    "prod-2": {
        "id": "prod-2",
        "name": "Wireless Mouse",
        "price": 29.99,
        "stock": 100,
        "images": ["mouse-1.jpg"]
    }
}

MOCK_ORDERS = [
    {
        "id": "order-1",
        "user_id": "user-123",
        "total": 159.98,
        "status": "delivered",
        "items": [
            {"product_id": "prod-2", "quantity": 2, "price": 29.99}
        ]
    }
]


class EcommerceBFF:
    """
    E-commerce BFF yang demonstrates berbagai use cases:
    - User personalization
    - Product recommendation
    - Cart management
    - Order tracking
    - Analytics aggregation
    """
    
    @staticmethod
    async def get_personalized_homepage(user_id: str, platform: str) -> Dict[str, Any]:
        """
        Homepage yang dipersonalisasi berdasarkan:
        - User behavior history
        - Platform (web vs mobile)
        - Time of day
        - User membership level
        """
        # Simulate fetching dari multiple services
        user_task = asyncio.create_task(EcommerceBFF._fetch_user(user_id))
        recommendations_task = asyncio.create_task(EcommerceBFF._fetch_recommendations(user_id))
        deals_task = asyncio.create_task(EcommerceBFF._fetch_daily_deals())
        
        user, recommendations, deals = await asyncio.gather(
            user_task, recommendations_task, deals_task
        )
        
        # Transform berdasarkan platform
        if platform == "mobile":
            # Mobile: Simplified homepage
            return {
                "user": {
                    "name": user["name"],
                    "cart_count": user["cart_items"]
                },
                "hero_deal": deals[0] if deals else None,
                "recommendations": recommendations[:4],  # Only 4 items
                "categories": ["Electronics", "Fashion", "Home"]  # Simplified
            }
        else:
            # Web: Full homepage
            return {
                "user": user,
                "hero_banner": deals[0] if deals else None,
                "daily_deals": deals[:6],
                "recommendations": recommendations[:12],
                "categories": [
                    {"name": "Electronics", "subcategories": ["Laptops", "Phones"]},
                    {"name": "Fashion", "subcategories": ["Men", "Women", "Kids"]},
                    {"name": "Home", "subcategories": ["Furniture", "Decor"]}
                ],
                "recently_viewed": await EcommerceBFF._fetch_recently_viewed(user_id)
            }
    
    @staticmethod
    async def get_product_page(product_id: str, user_id: Optional[str], platform: str) -> Dict[str, Any]:
        """
        Product page dengan data yang berbeda untuk web vs mobile
        """
        # Fetch product details
        product = MOCK_PRODUCTS.get(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        # Parallel fetch related data
        reviews_task = asyncio.create_task(EcommerceBFF._fetch_reviews(product_id))
        similar_task = asyncio.create_task(EcommerceBFF._fetch_similar_products(product_id))
        
        reviews, similar = await asyncio.gather(reviews_task, similar_task)
        
        if platform == "mobile":
            # Mobile: Minimal data
            return {
                "id": product["id"],
                "name": product["name"],
                "price": product["price"],
                "image": product["images"][0],  # Single image
                "stock_status": "in_stock" if product["stock"] > 0 else "out_of_stock",
                "rating": 4.5,
                "review_count": len(reviews),
                "similar_products": similar[:3]  # Only 3 similar items
            }
        else:
            # Web: Full data
            return {
                **product,
                "reviews": reviews[:20],  # 20 reviews
                "rating_breakdown": {
                    "5_star": 65,
                    "4_star": 20,
                    "3_star": 10,
                    "2_star": 3,
                    "1_star": 2
                },
                "similar_products": similar[:8],
                "frequently_bought_together": await EcommerceBFF._fetch_frequently_bought_together(product_id),
                "shipping_info": {
                    "free_shipping": product["price"] > 50,
                    "estimated_days": "3-5"
                }
            }
    
    @staticmethod
    async def get_checkout_data(user_id: str, platform: str) -> Dict[str, Any]:
        """
        Checkout page aggregates:
        - Cart items dengan product details
        - Saved addresses
        - Payment methods
        - Shipping options
        - Promo codes
        """
        # Fetch all checkout-related data in parallel
        cart_task = asyncio.create_task(EcommerceBFF._fetch_cart(user_id))
        addresses_task = asyncio.create_task(EcommerceBFF._fetch_addresses(user_id))
        payment_task = asyncio.create_task(EcommerceBFF._fetch_payment_methods(user_id))
        
        cart, addresses, payment_methods = await asyncio.gather(
            cart_task, addresses_task, payment_task
        )
        
        # Enrich cart items dengan product details
        for item in cart:
            product = MOCK_PRODUCTS.get(item["product_id"])
            if product:
                item["product_name"] = product["name"]
                item["product_image"] = product["images"][0]
        
        # Calculate totals
        subtotal = sum(item["price"] * item["quantity"] for item in cart)
        shipping = 0 if subtotal > 50 else 9.99
        tax = subtotal * 0.08
        total = subtotal + shipping + tax
        
        if platform == "mobile":
            # Mobile: Streamlined checkout
            return {
                "cart_items": cart,
                "summary": {
                    "subtotal": subtotal,
                    "shipping": shipping,
                    "tax": tax,
                    "total": total
                },
                "default_address": addresses[0] if addresses else None,
                "default_payment": payment_methods[0] if payment_methods else None
            }
        else:
            # Web: Detailed checkout
            return {
                "cart_items": cart,
                "summary": {
                    "subtotal": subtotal,
                    "shipping": shipping,
                    "tax": tax,
                    "discount": 0,
                    "total": total
                },
                "addresses": addresses,
                "payment_methods": payment_methods,
                "shipping_options": [
                    {"id": "standard", "name": "Standard (3-5 days)", "price": 9.99},
                    {"id": "express", "name": "Express (1-2 days)", "price": 19.99},
                    {"id": "overnight", "name": "Overnight", "price": 39.99}
                ],
                "promo_codes": await EcommerceBFF._fetch_available_promos(user_id)
            }
    
    # Helper methods (simulated backend calls)
    @staticmethod
    async def _fetch_user(user_id: str) -> Dict:
        await asyncio.sleep(0.1)  # Simulate network delay
        return MOCK_USERS.get(user_id, {})
    
    @staticmethod
    async def _fetch_recommendations(user_id: str) -> List[Dict]:
        await asyncio.sleep(0.15)
        return list(MOCK_PRODUCTS.values())
    
    @staticmethod
    async def _fetch_daily_deals() -> List[Dict]:
        await asyncio.sleep(0.1)
        return [{"product_id": "prod-1", "discount": 20}]
    
    @staticmethod
    async def _fetch_recently_viewed(user_id: str) -> List[Dict]:
        await asyncio.sleep(0.1)
        return []
    
    @staticmethod
    async def _fetch_reviews(product_id: str) -> List[Dict]:
        await asyncio.sleep(0.12)
        return [
            {"id": "r1", "user": "Alice", "rating": 5, "comment": "Great product!"},
            {"id": "r2", "user": "Bob", "rating": 4, "comment": "Good value"}
        ]
    
    @staticmethod
    async def _fetch_similar_products(product_id: str) -> List[Dict]:
        await asyncio.sleep(0.1)
        return [p for p in MOCK_PRODUCTS.values() if p["id"] != product_id]
    
    @staticmethod
    async def _fetch_frequently_bought_together(product_id: str) -> List[Dict]:
        await asyncio.sleep(0.1)
        return []
    
    @staticmethod
    async def _fetch_cart(user_id: str) -> List[Dict]:
        await asyncio.sleep(0.1)
        return [
            {"product_id": "prod-2", "quantity": 2, "price": 29.99}
        ]
    
    @staticmethod
    async def _fetch_addresses(user_id: str) -> List[Dict]:
        await asyncio.sleep(0.1)
        return [
            {"id": "addr-1", "street": "123 Main St", "city": "San Francisco", "default": True}
        ]
    
    @staticmethod
    async def _fetch_payment_methods(user_id: str) -> List[Dict]:
        await asyncio.sleep(0.1)
        return [
            {"id": "pm-1", "type": "card", "last4": "4242", "default": True}
        ]
    
    @staticmethod
    async def _fetch_available_promos(user_id: str) -> List[Dict]:
        await asyncio.sleep(0.1)
        return [
            {"code": "SAVE10", "discount": 10, "type": "percentage"}
        ]


# API Endpoints
@app.get("/api/homepage")
async def get_homepage(
    user_id: str,
    x_platform: str = Header(default="web", alias="X-Platform")
):
    """Homepage endpoint dengan platform detection"""
    try:
        data = await EcommerceBFF.get_personalized_homepage(user_id, x_platform)
        return data
    except Exception as e:
        logger.error(f"Homepage error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load homepage")


@app.get("/api/products/{product_id}")
async def get_product(
    product_id: str,
    user_id: Optional[str] = None,
    x_platform: str = Header(default="web", alias="X-Platform")
):
    """Product page endpoint"""
    try:
        data = await EcommerceBFF.get_product_page(product_id, user_id, x_platform)
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Product page error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load product")


@app.get("/api/checkout")
async def get_checkout(
    user_id: str,
    x_platform: str = Header(default="web", alias="X-Platform")
):
    """Checkout page endpoint"""
    try:
        data = await EcommerceBFF.get_checkout_data(user_id, x_platform)
        return data
    except Exception as e:
        logger.error(f"Checkout error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load checkout")


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "ecommerce-bff"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
