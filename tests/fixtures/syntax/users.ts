import { getPool } from "./db";

export function deleteUser(id: string): Promise<void> {
  return Promise.resolve();
}

export class UserService {
  purge(id: string): Promise<void> {
    return Promise.resolve();
  }
}

function hidden(): void {}
