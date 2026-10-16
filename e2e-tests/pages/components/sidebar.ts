import { Locator, Page } from "@playwright/test";

export class Sidebar {
  page: Page;
  private createNewAppButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.createNewAppButton = page
      .locator(".sidebar__new")
      .getByText("Add new");
  }

  async selectDatabaseAndTableByName(dbName: string, tableName: string) {
    await this.selectDatabaseByName(dbName);
    await this.selectTableByName(tableName);
  }

  async selectDatabaseByName(name: string) {
    await this.page.getByTitle(name).click();
  }

  clickCreateNewApplication() {
    return this.createNewAppButton.click();
  }

  async selectTableByName(name: string) {
    await this.page.getByText(name).click();
  }
}
