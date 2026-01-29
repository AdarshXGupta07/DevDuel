// utils/ApiResponse.ts
export class ApiResponse<T> {
  statusCode: number;
  message: string;
  data: T;

  constructor(statusCode: number, data: T, message = "Success") {
    this.statusCode = statusCode;
    this.message = message;
    this.data = data;
  }
}
