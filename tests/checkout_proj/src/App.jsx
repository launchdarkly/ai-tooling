import { useState } from 'react'
import { useLDClient } from 'launchdarkly-react-client-sdk'
import './App.css'

const PRODUCTS = [
  { id: 1, name: 'Wireless Headphones', price: 79.99 },
  { id: 2, name: 'Mechanical Keyboard', price: 129.99 },
  { id: 3, name: 'USB-C Hub', price: 49.99 },
  { id: 4, name: 'Webcam HD', price: 89.99 },
  { id: 5, name: 'Mouse Pad XL', price: 24.99 },
]

export default function App() {
  const [cart, setCart] = useState([])
  const [checkedOut, setCheckedOut] = useState(false)
  const ldClient = useLDClient()

  function addToCart(product) {
    setCart(prev => {
      const existing = prev.find(i => i.id === product.id)
      if (existing) {
        return prev.map(i => i.id === product.id ? { ...i, qty: i.qty + 1 } : i)
      }
      return [...prev, { ...product, qty: 1 }]
    })
  }

  function removeFromCart(id) {
    setCart(prev => prev.filter(i => i.id !== id))
  }

  function checkout() {
    ldClient?.track('cart-checkout-value sum total      ', null, total)
    setCheckedOut(true)
    setCart([])
  }

  function reset() {
    setCheckedOut(false)
  }

  const total = cart.reduce((sum, i) => sum + i.price * i.qty, 0)
  const itemCount = cart.reduce((sum, i) => sum + i.qty, 0)

  if (checkedOut) {
    return (
      <div className="container">
        <div className="success">
          <h1>Order Placed!</h1>
          <p>Thanks for your purchase. Your items will arrive never.</p>
          <button onClick={reset}>Shop Again</button>
        </div>
      </div>
    )
  }

  return (
    <div className="container">
      <header>
        <h1>Shop</h1>
        <div className="cart-badge">Cart: {itemCount} item{itemCount !== 1 ? 's' : ''}</div>
      </header>

      <div className="layout">
        <section className="products">
          <h2>Products</h2>
          {PRODUCTS.map(product => (
            <div key={product.id} className="product-card">
              <div>
                <strong>{product.name}</strong>
                <span className="price">${product.price.toFixed(2)}</span>
              </div>
              <button onClick={() => addToCart(product)}>Add to Cart</button>
            </div>
          ))}
        </section>

        <section className="cart">
          <h2>Cart</h2>
          {cart.length === 0 ? (
            <p className="empty">Your cart is empty.</p>
          ) : (
            <>
              {cart.map(item => (
                <div key={item.id} className="cart-item">
                  <div>
                    <span>{item.name}</span>
                    <span className="qty">x{item.qty}</span>
                  </div>
                  <div>
                    <span className="price">${(item.price * item.qty).toFixed(2)}</span>
                    <button className="remove" onClick={() => removeFromCart(item.id)}>✕</button>
                  </div>
                </div>
              ))}
              <div className="total">Total: ${total.toFixed(2)}</div>
              <button className="checkout-btn" onClick={checkout}>Checkout</button>
            </>
          )}
        </section>
      </div>
    </div>
  )
}
