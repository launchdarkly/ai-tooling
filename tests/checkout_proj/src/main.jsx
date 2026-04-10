import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { asyncWithLDProvider } from 'launchdarkly-react-client-sdk'
import App from './App.jsx'

const clientSideID = import.meta.env.VITE_LD_CLIENT_SIDE_ID

;(async () => {
  const LDProvider = await asyncWithLDProvider({
    clientSideID,
    context: { kind: 'user', anonymous: true },
    options: {
      baseUrl: import.meta.env.VITE_LD_BASE_URL,
      streamUrl: import.meta.env.VITE_LD_STREAM_URL,
      eventsUrl: import.meta.env.VITE_LD_EVENTS_URL,
    },
  })

  createRoot(document.getElementById('root')).render(
    <StrictMode>
      <LDProvider>
        <App />
      </LDProvider>
    </StrictMode>,
  )
})()
