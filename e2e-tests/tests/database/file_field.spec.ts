import { expect, test } from "../baserowTest";
import { createDatabase } from "../../fixtures/database/database";
import { createTable } from "../../fixtures/database/table";
import { TablePage } from "../../pages/database/tablePage";

test.describe("File field tests", () => {
  test("User can upload an image and download it again @upload", async ({
    page,
    goto,
    workspacePage,
  }) => {
    const user = workspacePage.user;
    const workspace = workspacePage.workspace;

    // Seed a database and a table with a single row through the API so the
    // test does not depend on any bundled application template.
    const database = await createDatabase(user, "File Field DB", workspace);
    const table = await createTable(user, "Files", database, [
      ["Name"],
      ["Row 1"],
    ]);

    const tablePage = new TablePage({ page, goto });
    await tablePage.goToTable(table);

    await tablePage.addNewFieldOfType("File");
    const imageWidth =
      await tablePage.uploadImageToFirstFileFieldCellAndGetWidth();

    expect(imageWidth).toBeGreaterThan(0);
  });
});
