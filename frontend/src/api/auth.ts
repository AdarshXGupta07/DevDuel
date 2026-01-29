import api from "./axios";

export const registerUser = (data: {
  username: string;
  email: string;
  password: string;
}) => api.post("/register", data);

export const loginUser = (data: {
  email: string;
  password: string;
}) => api.post("/login", data);

export const logoutUser = () => api.post("/logout");

export const getCurrentUser = () => api.get("/me");