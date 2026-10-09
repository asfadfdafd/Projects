export async function getServerSideProps() {
  return { redirect: { destination: "/documents", permanent: false } };
}

export default function Home() {
  return null;
}
