/** A server answered and said no (4xx) or failed (5xx). Network failures are plain Errors. */
export class HttpError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}
