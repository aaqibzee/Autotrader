import { describe, expectTypeOf, it } from "vitest";
import type {
  ApiMutationBody,
  ApiMutationPath,
  ApiMutationResponse,
  ApiPath,
  ApiResponse,
} from "./types";

// A fixture contract in openapi-typescript's shape: absent methods are optional `never`.
type Listing = { id: string; title: string };
interface FixturePaths {
  "/api/v1/listings": {
    get: { responses: { 200: { content: { "application/json": Listing[] } } } };
    post: {
      requestBody: { content: { "application/json": { title: string } } };
      responses: {
        201: { content: { "application/json": Listing } };
        422: { content: { "application/problem+json": unknown } };
      };
    };
    put?: never;
    patch?: never;
    delete?: never;
  };
  "/api/v1/listings/{id}/publish": {
    get?: never;
    post: { requestBody?: never; responses: { 204: { content?: never } } };
    put?: never;
    patch?: never;
    delete?: never;
  };
  "/health/live": {
    get: {
      responses: {
        200: { content: { "application/json": { status: string } } };
      };
    };
    post?: never;
    put?: never;
    patch?: never;
    delete?: never;
  };
}

describe("method-aware API types (Feature 03 A7)", () => {
  it("GET paths are the /api/v1 paths that define get", () => {
    expectTypeOf<ApiPath<FixturePaths>>().toEqualTypeOf<"/api/v1/listings">();
    expectTypeOf<ApiResponse<"/api/v1/listings", FixturePaths>>().toEqualTypeOf<
      Listing[]
    >();
  });

  it("mutation paths are the /api/v1 paths that define the method", () => {
    expectTypeOf<ApiMutationPath<"post", FixturePaths>>().toEqualTypeOf<
      "/api/v1/listings" | "/api/v1/listings/{id}/publish"
    >();
    expectTypeOf<
      ApiMutationPath<"delete", FixturePaths>
    >().toEqualTypeOf<never>();
  });

  it("bodies and responses come from the operation", () => {
    expectTypeOf<
      ApiMutationBody<"/api/v1/listings", "post", FixturePaths>
    >().toEqualTypeOf<{
      title: string;
    }>();
    expectTypeOf<
      ApiMutationResponse<"/api/v1/listings", "post", FixturePaths>
    >().toEqualTypeOf<Listing>();
    expectTypeOf<
      ApiMutationBody<"/api/v1/listings/{id}/publish", "post", FixturePaths>
    >().toEqualTypeOf<undefined>();
  });

  it("the real contract has a GET path", () => {
    expectTypeOf<"/api/v1/health/ready">().toExtend<ApiPath>();
  });
});
