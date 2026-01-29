import { Request, Response, NextFunction } from "express";
import { asyncHandler } from "../utils/asyncHandler";
import { ApiError } from "../utils/ApiError";
import jwt, { JwtPayload } from "jsonwebtoken";
import { User } from "../models/user.models";

interface TokenPayload extends JwtPayload {
  _id: string;
}

const verifyJWT = asyncHandler(async (req: Request, res: Response, next: NextFunction) => {
  const token = req.cookies?.accessToken || req.header("Authorization")?.replace("Bearer ", "");

  if (!token) {
    throw new ApiError(401, "Unauthorized request");
  }

  try {
    const decoded = jwt.verify(token, process.env.ACCESS_TOKEN_SECRET!) as string | TokenPayload;

    if (typeof decoded === "string" || !decoded._id) {
      throw new ApiError(401, "Invalid access token");
    }

    const user = await User.findById(decoded._id).select("-password -refreshToken");

    if (!user) {
      throw new ApiError(401, "Invalid access token");
    }

    req.user = user;
    next();
  } catch (error) {
    throw new ApiError(401, "Invalid access token");
  }
});

export { verifyJWT };