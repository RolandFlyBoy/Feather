/**
 * Feather API Utility
 * ===================
 * Centralized HTTP request handler with automatic CSRF protection.
 *
 * Features:
 * - Automatic CSRF token injection for state-changing requests
 * - Retry logic with exponential backoff
 * - Configurable timeouts
 * - Standardized response format
 * - File upload with progress tracking
 *
 * Usage:
 *   // Simple GET
 *   const result = await ApiUtility.get('/api/users');
 *
 *   // POST with data
 *   const result = await ApiUtility.post('/api/users', { name: 'John' });
 *
 *   // With options
 *   const result = await ApiUtility.request('/api/data', {
 *     method: 'POST',
 *     body: JSON.stringify(data),
 *     silent: true,  // Suppress error notifications
 *     timeout: 60000 // Custom timeout
 *   });
 *
 *   // File upload with progress
 *   const result = await ApiUtility.upload('/api/upload', formData, {
 *     onProgress: (percent) => console.log(`${percent}% complete`)
 *   });
 */

const ApiUtility = {
  /**
   * Default configuration
   */
  defaults: {
    timeout: 30000,    // 30 seconds
    retries: 2,        // Retry failed requests twice
    silent: false,     // Show error notifications by default
  },

  /**
   * Get CSRF token from meta tag
   * @returns {string} CSRF token or empty string
   */
  getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
  },

  /**
   * Helper to add CSRF token to fetch options
   * Use for direct fetch() calls: fetch(url, ApiUtility.withCsrf({ method: 'POST' }))
   *
   * @param {Object} options - Fetch options
   * @returns {Object} Options with CSRF header added
   */
  withCsrf(options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
      return {
        ...options,
        headers: {
          ...options.headers,
          'X-CSRFToken': this.getCsrfToken()
        }
      };
    }
    return options;
  },

  /**
   * Core request handler with retry logic
   *
   * @param {string} url - Request URL
   * @param {Object} options - Fetch options plus custom options
   * @param {number} [options.timeout] - Request timeout in ms
   * @param {number} [options.retries] - Number of retry attempts
   * @param {boolean} [options.silent] - Suppress error notifications
   * @returns {Promise<{success: boolean, data: any, error: any, meta: any}>}
   */
  async request(url, options = {}) {
    const config = { ...this.defaults, ...options };
    const { timeout, retries, silent } = config;

    // Set Accept header for JSON API detection
    options.headers = {
      'Accept': 'application/json',
      ...options.headers
    };

    // Add CSRF token for state-changing requests
    const method = (options.method || 'GET').toUpperCase();
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
      options.headers = {
        ...options.headers,
        'X-CSRFToken': this.getCsrfToken()
      };
    }

    let lastError = null;
    let attempt = 0;

    while (attempt <= retries) {
      try {
        // Create abort controller for timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);

        // Make request
        const response = await fetch(url, {
          ...options,
          signal: controller.signal
        });

        clearTimeout(timeoutId);

        // Parse JSON response
        const data = await response.json();

        // Handle HTTP errors
        if (!response.ok) {
          const error = new Error(data.error?.message || data.error || `HTTP ${response.status}`);
          error.response = response;
          error.data = data;
          throw error;
        }

        // Success - normalize response format
        return {
          success: data.success !== undefined ? data.success : true,
          data: data.data !== undefined ? data.data : data,
          error: data.error || null,
          meta: data.meta || null,
          response
        };

      } catch (error) {
        lastError = error;

        // Don't retry on abort or 4xx client errors
        if (error.name === 'AbortError' ||
            (error.response && error.response.status >= 400 && error.response.status < 500)) {
          break;
        }

        // Retry with exponential backoff
        attempt++;
        if (attempt <= retries) {
          const delay = Math.min(1000 * Math.pow(2, attempt), 5000);
          await new Promise(resolve => setTimeout(resolve, delay));
        }
      }
    }

    // Handle final failure
    if (!silent) {
      const errorMessage = lastError.data?.error?.message ||
                          lastError.data?.error ||
                          lastError.message ||
                          'Request failed';
      console.error('API Error:', errorMessage);
      // Hook point: Override this for custom error notifications
      if (typeof this.onError === 'function') {
        this.onError(errorMessage, lastError);
      }
    }

    return {
      success: false,
      data: lastError.data || null,
      error: lastError,
      meta: null
    };
  },

  /**
   * GET request
   * @param {string} url - Request URL
   * @param {Object} [options] - Additional options
   */
  async get(url, options = {}) {
    return this.request(url, { ...options, method: 'GET' });
  },

  /**
   * POST request with JSON body
   * @param {string} url - Request URL
   * @param {Object} [data] - Request body
   * @param {Object} [options] - Additional options
   */
  async post(url, data = {}, options = {}) {
    return this.request(url, {
      ...options,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {})
      },
      body: JSON.stringify(data)
    });
  },

  /**
   * PUT request with JSON body
   * @param {string} url - Request URL
   * @param {Object} [data] - Request body
   * @param {Object} [options] - Additional options
   */
  async put(url, data = {}, options = {}) {
    return this.request(url, {
      ...options,
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {})
      },
      body: JSON.stringify(data)
    });
  },

  /**
   * PATCH request with JSON body
   * @param {string} url - Request URL
   * @param {Object} [data] - Request body
   * @param {Object} [options] - Additional options
   */
  async patch(url, data = {}, options = {}) {
    return this.request(url, {
      ...options,
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {})
      },
      body: JSON.stringify(data)
    });
  },

  /**
   * DELETE request
   * @param {string} url - Request URL
   * @param {Object} [options] - Additional options
   */
  async delete(url, options = {}) {
    return this.request(url, { ...options, method: 'DELETE' });
  },

  /**
   * Upload file(s) with FormData
   * Supports progress tracking via onProgress callback
   *
   * @param {string} url - Upload URL
   * @param {FormData} formData - Form data with files
   * @param {Object} [options] - Additional options
   * @param {Function} [options.onProgress] - Progress callback (0-100)
   */
  async upload(url, formData, options = {}) {
    const { onProgress, ...requestOptions } = options;

    // Use XMLHttpRequest for progress tracking
    if (onProgress) {
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();

        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) {
            const percent = (e.loaded / e.total) * 100;
            onProgress(percent);
          }
        });

        xhr.addEventListener('load', () => {
          try {
            const data = JSON.parse(xhr.responseText);
            if (xhr.status >= 200 && xhr.status < 300) {
              resolve({
                success: data.success !== undefined ? data.success : true,
                data: data.data !== undefined ? data.data : data,
                error: data.error || null,
                meta: data.meta || null
              });
            } else {
              reject({
                success: false,
                data,
                error: data.error || `HTTP ${xhr.status}`
              });
            }
          } catch (e) {
            reject({ success: false, error: 'Invalid JSON response', data: null });
          }
        });

        xhr.addEventListener('error', () => {
          reject({ success: false, error: 'Network error', data: null });
        });

        xhr.timeout = requestOptions.timeout || this.defaults.timeout;
        xhr.addEventListener('timeout', () => {
          reject({ success: false, error: 'Request timeout', data: null });
        });

        xhr.open(requestOptions.method || 'POST', url);
        xhr.setRequestHeader('X-CSRFToken', this.getCsrfToken());
        xhr.setRequestHeader('Accept', 'application/json');
        xhr.send(formData);
      });
    }

    // Standard upload without progress
    return this.request(url, {
      ...requestOptions,
      method: requestOptions.method || 'POST',
      body: formData
    });
  },

  /**
   * Error handler hook - override for custom notifications
   * @param {string} message - Error message
   * @param {Error} error - Original error object
   */
  onError: null
};

// Export globally
window.ApiUtility = ApiUtility;
