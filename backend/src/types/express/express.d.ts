import { User } from "../models/user.models"; // adjust path if needed

declare global {
  namespace Express {
    interface Request {
      user: User; // or a more specific type (e.g. UserDocument) if you have one
    }
  }
}