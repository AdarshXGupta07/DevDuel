import mongoose from "mongoose";
import { DB_NAME } from "../constants";

export const connectDB = async () => {
    try {
        const MONGODB_URI = process.env.MONGODB_URI;
        
        if (!MONGODB_URI) {
            throw new Error("MONGODB_URI is not defined in environment variables");
        }
        
        await mongoose.connect(`${MONGODB_URI}/${DB_NAME}`);
        console.log('MongoDB connected');
    } 
    catch (error) {
        console.error('MongoDB connection error:', error);
        process.exit(1);
    }
};