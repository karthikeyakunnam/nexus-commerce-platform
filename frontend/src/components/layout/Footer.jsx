/**
 * Footer component with Tailwind CSS.
 */

function Footer() {
  return (
    <footer className="bg-white border-t border-gray-200 mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="text-center space-y-2">
          <p className="text-gray-900 font-medium">
            🎓 Educational Nexus Commerce Platform Project
          </p>
          <p className="text-sm text-gray-600 font-medium">
            Built with: Django REST Framework • gRPC • React • JWT • 2FA
          </p>
          <p className="text-xs text-gray-500 italic">
            Demonstrates: Service Isolation • Circuit Breaker • Retry Logic • Field Encryption
          </p>
        </div>
      </div>
    </footer>
  )
}

export default Footer
