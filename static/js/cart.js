function updateCart(productId, action, buttonElement) {
    fetch(`/api/update-cart/${productId}/${action}`)
        .then(response => response.json())
        .then(data => {
            document.getElementById(`quantity-${productId}`).innerText = data.quantity;
            document.getElementById('cart-total').innerText = data.total;

            if (data.quantity === 0) {
                document.getElementById(`row-${productId}`).remove();
            }
        });
}