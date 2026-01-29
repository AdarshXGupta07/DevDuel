import { asyncHandler } from "../utils/asyncHandler";
import { ApiError } from "../utils/ApiError";
import {ApiResponse} from "../utils/ApiResponse";
import {User} from "../models/user.models";
import {generateAccessToken,generateRefreshToken} from "../utils/token";
import { hashPassword,comparePasswords } from "../utils/hash";
import { Request, Response} from 'express';
import dotenv from "dotenv";
dotenv.config();

export const registerUser = asyncHandler(async (req:Request, res:Response) => {
  const { username, email, password } = req.body;

  if (!username || !email || !password) {
    throw new ApiError(400, "All fields are required");
  }

  const existingUser = await User.findOne({
    $or: [{ email }, { username }],
  });

  if (existingUser) {
    throw new ApiError(409, "User already exists");
  }

  // Hash the password before creating the user
  const hashedPassword = await hashPassword(password);
  
  const user = await User.create({
    username,
    email,
    password: hashedPassword, // Use the pre-hashed password
  });

  const safeUser = await User.findById(user._id).select("-password");

  return res
    .status(201)
    .json(new ApiResponse(201, safeUser, "User registered successfully"));
});

/**
 * LOGIN USER
 */
export const loginUser = asyncHandler(async (req: Request, res: Response) => {
  const { email, password } = req.body;
  console.log('Login attempt for email:', email);

  if (!email || !password) {
    console.log('Missing email or password');
    throw new ApiError(400, "Email and password are required");
  }

  // Trim and lowercase email for case-insensitive matching
  const normalizedEmail = email.trim().toLowerCase();
  
  const user = await User.findOne({ email: normalizedEmail }).select("+password");
  
  if (!user) {
    console.log('User not found with email:', normalizedEmail);
    throw new ApiError(401, "Invalid credentials");
  }

  console.log('User found, comparing password...');
  const isPasswordValid = await comparePasswords(password, user.password);

  if (!isPasswordValid) {
    console.log('Invalid password for user:', user.email);
    throw new ApiError(401, "Invalid credentials");
  }

  const accessToken = generateAccessToken({
    _id: user._id.toString(),
    email: user.email,
    username: user.username,
    role: user.role,
  });

  const refreshToken = generateRefreshToken({
    _id: user._id.toString(),
    email: user.email,
    username: user.username,
    role: user.role
  });

  // save refresh token
  user.refreshToken = refreshToken;
  await user.save({ validateBeforeSave: false });

  const loggedInUser = await User.findById(user._id).select("-password");

  const cookieOptions = {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict" as const,
  };

  return res
    .status(200)
    .cookie("accessToken", accessToken, cookieOptions)
    .cookie("refreshToken", refreshToken, cookieOptions)
    .json(
      new ApiResponse(
        200,
        { user: loggedInUser },
        "User logged in successfully"
      )
    );
});
