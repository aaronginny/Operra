export const metadata = { title: 'PhantomPilot', description: 'WhatsApp task management' }
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
