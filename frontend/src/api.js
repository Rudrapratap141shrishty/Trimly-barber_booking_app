const API_URL = (
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

export async function apiRequest(path, options = {}) {
  const token = localStorage.getItem("trimly_token");

  const headers = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers
  };

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.detail || "Request failed");
  }

  return data;
}

export async function registerUser(payload) {
  return apiRequest("/api/auth/register", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function loginUser(payload) {
  const data = await apiRequest("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(payload)
  });

  localStorage.setItem("trimly_token", data.access_token);

  return data;
}

export async function getBarbers() {
  return apiRequest("/api/barbers");
}

export async function getServices() {
  return apiRequest("/api/services");
}

export async function getAppointments() {
  return apiRequest("/api/appointments");
}

export async function createAppointment(payload) {
  return apiRequest("/api/appointments", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function cancelAppointment(id) {
  return apiRequest(`/api/appointments/${id}/cancel`, {
    method: "PATCH"
  });
}

export async function getAvailableSlots(barberId, serviceId, date) {
  const params = new URLSearchParams({
    barber_id: barberId,
    service_id: serviceId,
    date
  });

  return apiRequest(`/api/appointments/slots?${params}`);
}