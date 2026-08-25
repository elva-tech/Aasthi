import sys
import argparse
from rera_wrapper import KarnatakaRERAWrapper
from bescom_wrapper import BESCOMBillScraper
from water_bill_wrapper import WaterBillScraper
from property_tax_wrapper import BBMPPropertyTaxScraper
from kaveri import KaveriBot
from ekhata import EKhataBot
from ecourt import ECourtAutomation
class PropertyDocumentsWrapper:

    def __init__(
        self,
        project_name,
        bescom_account_id,
        water_rr_number,
        pid_number,
        owner_name,
        district,
        taluka,
        hobli,
        village,
        property_no,
        epid_number,
        court_party_name,
        court_year
    ):

        self.project_name = project_name
        self.bescom_account_id = bescom_account_id
        self.water_rr_number = water_rr_number
        self.pid_number = pid_number
        self.owner_name = owner_name
        self.district = district
        self.taluka = taluka
        self.hobli = hobli
        self.village = village
        self.property_no = property_no
        self.epid_number = epid_number
        self.court_party_name = court_party_name    
        self.court_year = court_year
    def run_all(self):
        # -------- RERA --------
        print(" RERA Automation")
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
            print(f" RERA Automation failed or timed out. Skipping. Error: {e}")

        # -------- BESCOM --------
        print(" BESCOM Automation")
        try:
            BESCOMBillScraper(self.bescom_account_id).run()
        except Exception as e:
            print(f"BESCOM failed: {e}")

        # -------- WATER BILL --------
        print("Water Bill Automation")
        try:
            water_data = WaterBillScraper(
                self.water_rr_number
            ).run()

            print(water_data)

        except Exception as e:
            print(f"Water Bill failed: {e}")

        # -------- PROPERTY TAX --------
        print("BBMP Property Tax Automation")
        try:

            BBMPPropertyTaxScraper(
                pid_number=self.pid_number,
                owner_name=self.owner_name,
            ).run()

        except Exception as e:

            print(f"BBMP Property Tax failed: {e}")
        # --------Kaveri EC  --------
        print("Kaveri EC Automation")

        try:
            bot = KaveriBot()
            bot.open_site()
            bot.login(
                username="pradhyumna.nov2004@gmail.com",
                password="OKjrjN9VZH",
                captcha_wait=40
            )
            bot.start_application()
            bot.open_ec()
            bot.enter_property_details(
                district=self.district,
                taluka=self.taluka,
                hobli=self.hobli,
                village=self.village,
                property_type="non_agricultural"
            )
            bot.enter_property_number(
                property_no=self.property_no
            )
            bot.search(
                captcha_wait=40,
                screenshot_out="ec_result.png"
            )
        except Exception as e:
            print(f"Kaveri EC failed: {e}")

        finally:
            try:
                bot.close()
            except:
                pass
        # -------- E-KHATA --------
        print("eKhata Automation")

        try:

            bot = EKhataBot()

            pdf_path = bot.run(
                search_type="epid",
                search_value=self.epid_number,
                wait_seconds=30
            )

            print("eKhata PDF:", pdf_path)

        except Exception as e:

            print(
                f"eKhata Automation failed: {e}"
            )

        finally:

            try:
                bot.close()
            except:
                pass
        # -------- ECOURT --------
        print("eCourt Automation")

        try:

            ecourt = ECourtAutomation()

            ecourt.run(
                party_name=self.court_party_name,
                year=self.court_year,
                max_courts=20,
                captcha_wait=40
            )

            print("eCourt completed")

        except Exception as e:

            print(
                f"eCourt Automation failed: {e}"
            )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run property document collection wrappers')
    parser.add_argument('--project-name', default='Prestige Lakeside Habitat', help='Project name')
    parser.add_argument('--bescom-account', default='7220755000', help='BESCOM account ID')
    parser.add_argument('--water-rr', default='N-435608', help='Water RR number')
    parser.add_argument('--pid-number', default='1500082907', help='PID number')
    parser.add_argument('--owner-name', default='RAM', help='Owner name')
    parser.add_argument('--district', default='Bangalore', help='District')
    parser.add_argument('--taluka', default='Bangalore', help='Taluka')
    parser.add_argument('--hobli', default='Bangalore', help='Hobli')
    parser.add_argument('--village', default='Bangalore', help='Village')
    parser.add_argument("--property-no",default="45")
    parser.add_argument('--epid-number',default='2737828078',help='Property ePID')
    parser.add_argument('--court-party-name',default='Prestige Estates')
    parser.add_argument('--court-year', default='2015')
    args = parser.parse_args()
    
    wrapper = PropertyDocumentsWrapper(
    project_name=args.project_name,
    bescom_account_id=args.bescom_account,
    water_rr_number=args.water_rr,
    pid_number=args.pid_number,
    owner_name=args.owner_name,
    district=args.district,
    taluka=args.taluka,
    hobli=args.hobli,
    village=args.village,
    property_no=args.property_no,
    epid_number=args.epid_number,
    court_party_name=args.court_party_name,
    court_year=args.court_year
)
    wrapper.run_all()