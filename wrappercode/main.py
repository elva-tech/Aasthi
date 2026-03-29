from rera_wrapper import KarnatakaRERAWrapper
from bescom_wrapper import BESCOMBillScraper
from water_bill_wrapper import WaterBillScraper
from property_tax_wrapper import BBMPPropertyTaxScraper


class PropertyDocumentsWrapper:

    def __init__(self, project_name, bescom_account_id,
                 water_rr_number, pid_number, owner_name, application_number):

        self.project_name = project_name
        self.bescom_account_id = bescom_account_id
        self.water_rr_number = water_rr_number
        self.pid_number = pid_number
        self.owner_name = owner_name
        self.application_number = application_number

    def run_all(self):
        # -------- RERA --------
        print("🔹 RERA Automation")
        try:
            rera = KarnatakaRERAWrapper(self.project_name)
            try:
                rera.open_project()
                rera.download_completion_documents()
                rera.download_uploaded_documents()
                rera.download_enquired_documents()
            finally:
                rera.close()
        except Exception as e:
            print(f"⚠️ RERA Automation failed or timed out. Skipping. Error: {e}")

        # -------- BESCOM --------
        print("🔹 BESCOM Automation")
        BESCOMBillScraper(self.bescom_account_id).run()

        # -------- WATER BILL --------
        print("🔹 Water Bill Automation")
        water_data = WaterBillScraper(self.water_rr_number).run()
        print(water_data)

        # -------- PROPERTY TAX --------
        print("🔹 BBMP Property Tax Automation")
        BBMPPropertyTaxScraper(
            pid_number=self.pid_number,
            owner_name=self.owner_name,
            application_number=self.application_number
        ).run()

        print("✅ ALL PROPERTY AUTOMATIONS COMPLETED")


if __name__ == "__main__":
    wrapper = PropertyDocumentsWrapper(
        project_name="Prestige Lakeside Habitat",
        bescom_account_id="7220755000",
        water_rr_number="N-435608",
        pid_number="1500082907",
        owner_name="RAM",
        application_number="1500082907"
    )
    wrapper.run_all()