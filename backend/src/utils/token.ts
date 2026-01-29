import { sign, Secret, SignOptions } from "jsonwebtoken";
import { env } from "../config/env";

type ExpiresIn = SignOptions["expiresIn"];

export const generateAccessToken = (payload: object): string => {
  const expiresIn: ExpiresIn = env.ACCESS_TOKEN_EXPIRY as ExpiresIn;

  return sign(
    payload,
    env.ACCESS_TOKEN_SECRET as Secret,
    { expiresIn }
  );
};

export const generateRefreshToken = (payload: object): string => {
  const expiresIn: ExpiresIn = env.REFRESH_TOKEN_EXPIRY as ExpiresIn;

  return sign(
    payload,
    env.REFRESH_TOKEN_SECRET as Secret,
    { expiresIn }
  );
};
