import axios from 'axios'
import { clearAuthCookies } from './cookies'

// Authentication tokens are HttpOnly cookies set by UserService. JavaScript
// never reads, stores, or copies JWT values into an Authorization header.
const axiosInstance = axios.create({
  baseURL: '/',
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
})

let isRefreshing = false
let failedQueue = []

const processQueue = (error) => {
  failedQueue.forEach(({ resolve, reject }) => {
    if (error) reject(error)
    else resolve()
  })
  failedQueue = []
}

async function refreshSession() {
  // CookieTokenRefreshView reads the refresh token from the HttpOnly cookie.
  await axios.post('/api/token/refresh/', {}, { withCredentials: true })
}

axiosInstance.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config || {}
    const isAuthEndpoint = originalRequest.url?.includes('/api/token/')

    if (error.response?.status !== 401 || originalRequest._retry || isAuthEndpoint) {
      return Promise.reject(error)
    }

    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        failedQueue.push({ resolve, reject })
      }).then(() => axiosInstance(originalRequest))
    }

    originalRequest._retry = true
    isRefreshing = true
    try {
      await refreshSession()
      processQueue(null)
      return axiosInstance(originalRequest)
    } catch (refreshError) {
      processQueue(refreshError)
      clearAuthCookies()
      if (window.location.pathname !== '/login') window.location.href = '/login'
      return Promise.reject(refreshError)
    } finally {
      isRefreshing = false
    }
  },
)

export default axiosInstance
