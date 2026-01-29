# DevDuel Project Dependencies Analysis

## Project Structure
```
DevDuel/
├── backend/          # Node.js + Express + TypeScript
│   ├── src/
│   │   ├── config/    # DB & env config
│   │   ├── controllers/ # users, duels
│   │   ├── middlewares/ # auth
│   │   ├── models/    # MongoDB models
│   │   ├── routes/    # API routes
│   │   ├── types/     # TypeScript types
│   │   └── utils/     # utilities
│   └── package.json   # backend deps
├── frontend/          # TypeScript API layer
│   └── src/api/       # auth, axios services
└── package.json       # root (legacy)
```

## Backend Dependencies

### Production
- **axios** (^1.13.2) - HTTP client
- **bcrypt** (^5.1.0) + **bcryptjs** (^3.0.3) - Password hashing
- **cookie-parser** (^1.4.7) - Cookie middleware
- **cors** (^2.8.5) - CORS middleware
- **dotenv** (^16.4.5) - Environment variables
- **express** (^4.19.2) - Web framework
- **express-rate-limit** (^7.3.0) - Rate limiting
- **jsonwebtoken** (^9.0.2) - JWT tokens
- **mongoose** (^8.5.1) - MongoDB ODM
- **socket.io** (^4.7.5) - Real-time communication
- **winston** (^3.13.0) - Logging
- **zod** (^3.23.8) - Schema validation

### Type Definitions
- @types/bcrypt, @types/cookie-parser, @types/express, @types/jsonwebtoken, @types/node

### Development
- **nodemon** (^3.1.4) - Auto-restart
- **ts-node** (^10.9.2) - TypeScript execution
- **typescript** (^5.5.4) - TypeScript compiler

## Frontend Dependencies
- **axios** (^1.13.2) - HTTP client
- Missing: package.json, typescript, @types/node

## Root (Legacy) Dependencies
- cloudinary, mongoose-aggregate-paginate-v2, multer (unused)

## Key Features by Dependency
- **Auth**: bcrypt, jsonwebtoken, cookie-parser
- **Database**: mongoose (MongoDB)
- **Real-time**: socket.io (live duels)
- **API**: express, cors, axios
- **Validation**: zod
- **Dev**: typescript, nodemon
